from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_FREQUENCIES = {"1d", "60m", "30m", "15m"}
SUPPORTED_MARKET = "a_share"


@dataclass(frozen=True)
class Bar:
    symbol: str
    name: str
    market: str
    exchange: str
    frequency: str
    trade_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adj_factor: float
    source: str


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path, schema_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))


def parse_bar(row: dict[str, str]) -> Bar:
    bar = Bar(
        symbol=row["symbol"].strip().upper(),
        name=row["name"].strip(),
        market=row["market"].strip(),
        exchange=row["exchange"].strip().upper(),
        frequency=row["frequency"].strip(),
        trade_time=row["trade_time"].strip(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
        adj_factor=float(row.get("adj_factor") or 1.0),
        source=row.get("source", "unknown").strip() or "unknown",
    )
    validate_bar(bar)
    return bar


def validate_bar(bar: Bar) -> None:
    if bar.market != SUPPORTED_MARKET:
        raise ValueError(f"unsupported market: {bar.market}")
    if bar.frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"unsupported frequency: {bar.frequency}")
    if not bar.symbol.endswith((".SH", ".SZ")):
        raise ValueError(f"A-share symbol must end with .SH or .SZ: {bar.symbol}")
    if bar.exchange not in {"SH", "SZ"}:
        raise ValueError(f"unsupported exchange: {bar.exchange}")
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        raise ValueError(f"prices must be positive: {bar.symbol} {bar.trade_time}")
    if bar.high < max(bar.open, bar.close, bar.low):
        raise ValueError(f"high price is inconsistent: {bar.symbol} {bar.trade_time}")
    if bar.low > min(bar.open, bar.close, bar.high):
        raise ValueError(f"low price is inconsistent: {bar.symbol} {bar.trade_time}")
    if bar.volume < 0 or bar.amount < 0:
        raise ValueError(f"volume and amount must be non-negative: {bar.symbol}")


def read_csv(csv_path: Path) -> list[Bar]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [parse_bar(row) for row in csv.DictReader(handle)]


def insert_bars(conn: sqlite3.Connection, bars: Iterable[Bar]) -> int:
    count = 0
    for bar in bars:
        upsert_instrument(conn, bar)
        conn.execute(
            """
            INSERT INTO bars(
              symbol, frequency, trade_time, open, high, low, close,
              volume, amount, adj_factor, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, frequency, trade_time) DO UPDATE SET
              open = excluded.open,
              high = excluded.high,
              low = excluded.low,
              close = excluded.close,
              volume = excluded.volume,
              amount = excluded.amount,
              adj_factor = excluded.adj_factor,
              source = excluded.source
            """,
            (
                bar.symbol,
                bar.frequency,
                bar.trade_time,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.amount,
                bar.adj_factor,
                bar.source,
            ),
        )
        count += 1
    return count


def upsert_instrument(conn: sqlite3.Connection, bar: Bar) -> None:
    conn.execute(
        """
        INSERT INTO instruments(symbol, name, market, exchange, asset_type, status, updated_at)
        VALUES (?, ?, ?, ?, 'stock', 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
          name = excluded.name,
          market = excluded.market,
          exchange = excluded.exchange,
          updated_at = CURRENT_TIMESTAMP
        """,
        (bar.symbol, bar.name, bar.market, bar.exchange),
    )


def import_csv(db_path: Path, csv_path: Path) -> int:
    bars = read_csv(csv_path)
    if not bars:
        return 0

    symbol = bars[0].symbol
    frequency = bars[0].frequency
    source = bars[0].source

    with connect(db_path) as conn:
        for bar in bars:
            upsert_instrument(conn, bar)
        load_id = conn.execute(
            """
            INSERT INTO data_loads(source, symbol, frequency, status)
            VALUES (?, ?, ?, 'running')
            """,
            (source, symbol, frequency),
        ).lastrowid
        try:
            count = insert_bars(conn, bars)
            conn.execute(
                """
                UPDATE data_loads
                SET status = 'completed', finished_at = CURRENT_TIMESTAMP, row_count = ?
                WHERE id = ?
                """,
                (count, load_id),
            )
            return count
        except Exception as exc:
            conn.execute(
                """
                UPDATE data_loads
                SET status = 'failed', finished_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
                """,
                (str(exc), load_id),
            )
            raise


def query_bars(
    db_path: Path,
    symbol: str,
    frequency: str,
    start: str | None,
    end: str | None,
) -> list[dict[str, object]]:
    sql = """
        SELECT symbol, frequency, trade_time, open, high, low, close, volume, amount, adj_factor, source
        FROM bars
        WHERE symbol = ? AND frequency = ?
    """
    params: list[object] = [symbol.upper(), frequency]
    if start:
        sql += " AND trade_time >= ?"
        params.append(start)
    if end:
        sql += " AND trade_time <= ?"
        params.append(end)
    sql += " ORDER BY trade_time ASC"

    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def data_health(db_path: Path) -> dict[str, object]:
    with connect(db_path) as conn:
        instruments = conn.execute("SELECT COUNT(*) AS count FROM instruments").fetchone()["count"]
        bars = conn.execute("SELECT COUNT(*) AS count FROM bars").fetchone()["count"]
        coverage = [
            dict(row)
            for row in conn.execute(
                """
                SELECT symbol, frequency, COUNT(*) AS rows, MIN(trade_time) AS start_time, MAX(trade_time) AS end_time
                FROM bars
                GROUP BY symbol, frequency
                ORDER BY symbol, frequency
                """
            )
        ]
    return {"instrument_count": instruments, "bar_count": bars, "coverage": coverage}


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share market data module")
    parser.add_argument("--db", default="data_module/market_data.sqlite", help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create database schema")
    init_parser.add_argument("--schema", default="data_module/schema.sql")

    import_parser = subparsers.add_parser("import-csv", help="Import A-share OHLCV CSV")
    import_parser.add_argument("csv_path")

    query_parser = subparsers.add_parser("query", help="Query bars")
    query_parser.add_argument("--symbol", required=True)
    query_parser.add_argument("--frequency", required=True)
    query_parser.add_argument("--start")
    query_parser.add_argument("--end")

    subparsers.add_parser("health", help="Show data coverage")

    args = parser.parse_args()
    db_path = Path(args.db)

    if args.command == "init":
        init_db(db_path, Path(args.schema))
        print(f"initialized {db_path}")
    elif args.command == "import-csv":
        count = import_csv(db_path, Path(args.csv_path))
        print(f"imported {count} rows from {args.csv_path}")
    elif args.command == "query":
        rows = query_bars(db_path, args.symbol, args.frequency, args.start, args.end)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.command == "health":
        print(json.dumps(data_health(db_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
