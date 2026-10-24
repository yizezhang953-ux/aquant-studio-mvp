"""Research market-data store (SQLite) for A-shares and Hong Kong stocks.

Commands:
  init                     create / migrate the schema (v1 databases are upgraded in place)
  import-csv FILE          import an OHLCV CSV (see sample_data/*.csv for the columns)
  query --symbol --frequency [--start --end]
  health                   coverage summary

Real data: use data_module/fetch_market_data.py (Tencent quotes, HKEX board lots, HKD/CNY rates).
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_rules_module.market_rules import normalize_symbol  # noqa: E402


SUPPORTED_FREQUENCIES = {"1d", "60m", "30m", "15m"}
SUPPORTED_MARKETS = {"a_share", "hk_stock"}
EXCHANGES = {"a_share": {"SH", "SZ", "BJ"}, "hk_stock": {"HK"}}
CURRENCY = {"a_share": "CNY", "hk_stock": "HKD"}
DEFAULT_SCHEMA = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = "2"


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


def market_for_symbol(symbol: str) -> tuple[str, str]:
    """(market, exchange) for a normalised symbol."""
    exchange = symbol.rsplit(".", 1)[-1] if "." in symbol else ""
    if exchange == "HK":
        return "hk_stock", "HK"
    if exchange in {"SH", "SZ", "BJ"}:
        return "a_share", exchange
    raise ValueError(f"unsupported symbol (expected 600519.SH / 000001.SZ / 430047.BJ / 00700.HK): {symbol}")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row[0] if row else None


def migrate(conn: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA) -> None:
    """Create the v2 schema, upgrading a v1 (A-share only) database in place."""
    instruments_sql = _table_sql(conn, "instruments")
    if instruments_sql and "market = 'a_share'" in instruments_sql:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA legacy_alter_table = ON")  # keep bars' FK pointing at "instruments"
        conn.executescript(
            """
            ALTER TABLE instruments RENAME TO instruments_v1;
            ALTER TABLE data_loads RENAME TO data_loads_v1;
            """
        )
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.executescript(
            """
            INSERT INTO instruments(symbol, name, market, exchange, asset_type, currency, listed_date, status, created_at, updated_at)
            SELECT symbol, name, market, exchange, asset_type, 'CNY', listed_date, status, created_at, updated_at FROM instruments_v1;
            INSERT INTO data_loads(id, source, symbol, frequency, started_at, finished_at, row_count, status, error_message)
            SELECT id, source, symbol, frequency, started_at, finished_at, row_count, status, error_message FROM data_loads_v1;
            DROP TABLE instruments_v1;
            DROP TABLE data_loads_v1;
            """
        )
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def init_db(db_path: Path, schema_path: Path = DEFAULT_SCHEMA) -> None:
    with connect(db_path) as conn:
        migrate(conn, Path(schema_path))


def parse_bar(row: dict[str, str]) -> Bar:
    symbol = normalize_symbol(row["symbol"])
    market, exchange = market_for_symbol(symbol)
    bar = Bar(
        symbol=symbol,
        name=(row.get("name") or symbol).strip(),
        market=(row.get("market") or market).strip(),
        exchange=(row.get("exchange") or exchange).strip().upper(),
        frequency=row["frequency"].strip(),
        trade_time=row["trade_time"].strip(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume") or 0),
        amount=float(row.get("amount") or 0),
        adj_factor=float(row.get("adj_factor") or 1.0),
        source=(row.get("source") or "unknown").strip() or "unknown",
    )
    validate_bar(bar)
    return bar


def validate_bar(bar: Bar) -> None:
    if bar.market not in SUPPORTED_MARKETS:
        raise ValueError(f"unsupported market: {bar.market} (use a_share or hk_stock; 港股通 is chosen per strategy)")
    if bar.frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"unsupported frequency: {bar.frequency}")
    expected_market, expected_exchange = market_for_symbol(bar.symbol)
    if bar.market != expected_market or bar.exchange != expected_exchange:
        raise ValueError(f"symbol {bar.symbol} does not match market/exchange {bar.market}/{bar.exchange}")
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        raise ValueError(f"prices must be positive: {bar.symbol} {bar.trade_time}")
    if bar.high < max(bar.open, bar.close, bar.low):
        raise ValueError(f"high price is inconsistent: {bar.symbol} {bar.trade_time}")
    if bar.low > min(bar.open, bar.close, bar.high):
        raise ValueError(f"low price is inconsistent: {bar.symbol} {bar.trade_time}")
    if bar.volume < 0 or bar.amount < 0:
        raise ValueError(f"volume and amount must be non-negative: {bar.symbol}")
    if bar.adj_factor <= 0:
        raise ValueError(f"adj_factor must be positive: {bar.symbol} {bar.trade_time}")


def read_csv(csv_path: Path) -> list[Bar]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [parse_bar(row) for row in csv.DictReader(handle)]


def upsert_instrument(
    conn: sqlite3.Connection,
    symbol: str,
    name: str,
    market: str | None = None,
    exchange: str | None = None,
    lot_size: int | None = None,
    connect_eligible: bool | None = None,
) -> None:
    detected_market, detected_exchange = market_for_symbol(symbol)
    market = market or detected_market
    exchange = exchange or detected_exchange
    conn.execute(
        """
        INSERT INTO instruments(symbol, name, market, exchange, asset_type, currency, lot_size, connect_eligible, status, updated_at)
        VALUES (?, ?, ?, ?, 'stock', ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
          name = CASE WHEN excluded.name = excluded.symbol THEN instruments.name ELSE excluded.name END,
          market = excluded.market,
          exchange = excluded.exchange,
          currency = excluded.currency,
          lot_size = COALESCE(excluded.lot_size, instruments.lot_size),
          connect_eligible = COALESCE(excluded.connect_eligible, instruments.connect_eligible),
          updated_at = CURRENT_TIMESTAMP
        """,
        (symbol, name or symbol, market, exchange, CURRENCY[market], lot_size,
         None if connect_eligible is None else int(bool(connect_eligible))),
    )


def insert_bars(conn: sqlite3.Connection, bars: Iterable[Bar]) -> int:
    rows = []
    seen: set[str] = set()
    for bar in bars:
        if bar.symbol not in seen:
            upsert_instrument(conn, bar.symbol, bar.name, bar.market, bar.exchange)
            seen.add(bar.symbol)
        rows.append((bar.symbol, bar.frequency, bar.trade_time, bar.open, bar.high, bar.low, bar.close,
                     bar.volume, bar.amount, bar.adj_factor, bar.source))
    conn.executemany(
        """
        INSERT INTO bars(symbol, frequency, trade_time, open, high, low, close, volume, amount, adj_factor, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, frequency, trade_time) DO UPDATE SET
          open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
          volume = excluded.volume, amount = excluded.amount, adj_factor = excluded.adj_factor,
          source = excluded.source
        """,
        rows,
    )
    return len(rows)


def upsert_corporate_actions(conn: sqlite3.Connection, symbol: str, actions: Iterable[dict], source: str,
                             start: str | None = None, end: str | None = None) -> int:
    """Replace ``source``'s actions for ``symbol`` inside [start, end] (all of them when no window)."""
    rows = [(symbol, a["ex_date"], float(a.get("cash_dividend") or 0), float(a.get("bonus_ratio") or 0),
             a.get("currency"), source) for a in actions]
    sql, params = "DELETE FROM corporate_actions WHERE symbol = ? AND source = ?", [symbol, source]
    if start:
        sql += " AND ex_date >= ?"
        params.append(start)
    if end:
        sql += " AND ex_date <= ?"
        params.append(end)
    conn.execute(sql, params)
    conn.executemany(
        "INSERT OR REPLACE INTO corporate_actions(symbol, ex_date, cash_dividend, bonus_ratio, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def effective_actions(conn: sqlite3.Connection, symbol: str) -> list[dict]:
    """Corporate actions with explicit (non *_derived) rows winning on the same ex-date."""
    by_day: dict[str, list[dict]] = {}
    for row in conn.execute("SELECT ex_date, cash_dividend, bonus_ratio, source FROM corporate_actions WHERE symbol = ? ORDER BY ex_date", (symbol,)):
        by_day.setdefault(row["ex_date"], []).append(dict(row))
    chosen = []
    for day in sorted(by_day):
        explicit = [a for a in by_day[day] if not (a["source"] or "").endswith("_derived")]
        chosen.extend(explicit or by_day[day])
    return chosen


def rebuild_adj_factors(conn: sqlite3.Connection, symbol: str) -> int:
    """Recompute adj_factor for every stored bar of ``symbol`` from raw daily closes + actions."""
    from data_module.adjust import factors_from_actions

    daily = conn.execute("SELECT trade_time, close FROM bars WHERE symbol = ? AND frequency = '1d' ORDER BY trade_time", (symbol,)).fetchall()
    if not daily:
        return 0
    days = [r["trade_time"][:10] for r in daily]
    factors = factors_from_actions(days, [float(r["close"]) for r in daily], effective_actions(conn, symbol))
    by_day = dict(zip(days, factors))
    conn.executemany("UPDATE bars SET adj_factor = ? WHERE symbol = ? AND frequency = '1d' AND trade_time = ?",
                     [(f, symbol, r["trade_time"]) for r, f in zip(daily, factors)])
    for row in conn.execute("SELECT DISTINCT substr(trade_time, 1, 10) AS day FROM bars WHERE symbol = ? AND frequency != '1d'", (symbol,)).fetchall():
        if row["day"] in by_day:
            conn.execute("UPDATE bars SET adj_factor = ? WHERE symbol = ? AND frequency != '1d' AND substr(trade_time, 1, 10) = ?",
                         (by_day[row["day"]], symbol, row["day"]))
    return len(daily)


def upsert_fx_rates(conn: sqlite3.Connection, pair: str, rates: dict[str, float], source: str) -> int:
    conn.executemany(
        "INSERT INTO fx_rates(pair, rate_date, rate, source) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(pair, rate_date) DO UPDATE SET rate = excluded.rate, source = excluded.source",
        [(pair, day, float(rate), source) for day, rate in sorted(rates.items())],
    )
    return len(rates)


def set_board_lots(conn: sqlite3.Connection, lots: dict[str, int]) -> int:
    """lots: {'00700': 100, ...} from the HKEX securities list. Updates known HK instruments."""
    updated = 0
    for row in conn.execute("SELECT symbol FROM instruments WHERE market = 'hk_stock'").fetchall():
        code = row["symbol"].split(".")[0]
        if code in lots:
            conn.execute("UPDATE instruments SET lot_size = ? WHERE symbol = ?", (int(lots[code]), row["symbol"]))
            updated += 1
    return updated


def start_load(conn: sqlite3.Connection, source: str, symbol: str, frequency: str) -> int:
    return conn.execute(
        "INSERT INTO data_loads(source, symbol, frequency, status) VALUES (?, ?, ?, 'running')",
        (source, symbol, frequency),
    ).lastrowid


def finish_load(conn: sqlite3.Connection, load_id: int, count: int = 0, error: str | None = None) -> None:
    conn.execute(
        "UPDATE data_loads SET status = ?, finished_at = CURRENT_TIMESTAMP, row_count = ?, error_message = ? WHERE id = ?",
        ("failed" if error else "completed", count, error, load_id),
    )


def import_csv(db_path: Path, csv_path: Path) -> int:
    bars = read_csv(csv_path)
    if not bars:
        return 0
    with connect(db_path) as conn:
        migrate(conn)
        load_id = start_load(conn, bars[0].source, bars[0].symbol, bars[0].frequency)
        try:
            count = insert_bars(conn, bars)
        except Exception as exc:
            finish_load(conn, load_id, error=str(exc))
            raise
        finish_load(conn, load_id, count)
        return count


def query_bars(db_path: Path, symbol: str, frequency: str, start: str | None, end: str | None) -> list[dict[str, object]]:
    sql = """
        SELECT symbol, frequency, trade_time, open, high, low, close, volume, amount, adj_factor, source
        FROM bars WHERE symbol = ? AND frequency = ?
    """
    params: list[object] = [normalize_symbol(symbol), frequency]
    if start:
        sql += " AND trade_time >= ?"
        params.append(start)
    if end:
        sql += " AND trade_time <= ?"
        params.append(end if len(end) > 10 else f"{end} 23:59:59")
    sql += " ORDER BY trade_time ASC"
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def data_health(db_path: Path) -> dict[str, object]:
    with connect(db_path) as conn:
        migrate(conn)
        instruments = conn.execute("SELECT COUNT(*) AS count FROM instruments").fetchone()["count"]
        bars = conn.execute("SELECT COUNT(*) AS count FROM bars").fetchone()["count"]
        coverage = [
            dict(row)
            for row in conn.execute(
                """
                SELECT b.symbol, i.market, i.lot_size, b.frequency, COUNT(*) AS rows,
                       MIN(b.trade_time) AS start_time, MAX(b.trade_time) AS end_time
                FROM bars b JOIN instruments i ON i.symbol = b.symbol
                GROUP BY b.symbol, b.frequency ORDER BY b.symbol, b.frequency
                """
            )
        ]
        fx = [dict(row) for row in conn.execute(
            "SELECT pair, COUNT(*) AS rows, MIN(rate_date) AS start_date, MAX(rate_date) AS end_date FROM fx_rates GROUP BY pair"
        )]
        actions = conn.execute("SELECT COUNT(*) AS count FROM corporate_actions").fetchone()["count"]
    return {"instrument_count": instruments, "bar_count": bars, "coverage": coverage,
            "fx_rates": fx, "corporate_action_count": actions}


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant research market data (A-share / HK)")
    parser.add_argument("--db", default="data_module/market_data.sqlite", help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create or migrate database schema")
    init_parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))

    import_parser = subparsers.add_parser("import-csv", help="Import OHLCV CSV")
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
