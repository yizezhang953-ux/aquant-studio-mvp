"""Download real daily data into the research database (run on a machine with internet access).

Examples:
  python data_module/fetch_market_data.py --symbols 600519.SH 000001.SZ 00700.HK 00168.HK --start 2016-01-01
  python data_module/fetch_market_data.py --symbols 00700.HK --start 2016-01-01 --board-lots --fx
  python data_module/fetch_market_data.py --fx --start 2016-01-01           # only HKD/CNY rates

What is stored:
  * bars: raw daily OHLCV + adj_factor (forward-adjust factor) from Tencent;
  * instruments: name, market, currency, HK board lot (--board-lots, from the HKEX securities list);
  * fx_rates: HKDCNY daily reference rates (--fx), needed for 港股通 backtests.
Dividend ex-dates/amounts are inferred from the raw vs adjusted series and stored as
corporate_actions (source 'tencent_derived'). Exact actions loaded with ``--import-actions FILE.csv``
(columns: symbol, ex_date, cash_dividend, bonus_ratio) take precedence on the same ex-date.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module import market_data as md  # noqa: E402
from data_module.sources import fx as fx_source  # noqa: E402
from data_module.sources import hkex, tencent  # noqa: E402
from market_rules_module.market_rules import normalize_symbol  # noqa: E402


def fetch_symbol(conn, symbol: str, start: str, end: str) -> int:
    symbol = normalize_symbol(symbol)
    market, exchange = md.market_for_symbol(symbol)
    load_id = md.start_load(conn, tencent.SOURCE, symbol, "1d")
    try:
        result = tencent.fetch_daily_with_actions(symbol, start, end)
        rows = result["bars"]
        if not rows:
            raise RuntimeError("no bars returned (check the symbol and date range)")
        name = tencent.fetch_name(symbol) or symbol
        md.upsert_instrument(conn, symbol, name, market, exchange)
        bars = [md.Bar(name=name, market=market, exchange=exchange, **row) for row in rows]
        for bar in bars:
            md.validate_bar(bar)
        count = md.insert_bars(conn, bars)
        currency = "HKD" if market == "hk_stock" else "CNY"
        md.upsert_corporate_actions(conn, symbol, [{**a, "currency": currency} for a in result["actions"]],
                                    "tencent_derived", rows[0]["trade_time"], rows[-1]["trade_time"])
        md.rebuild_adj_factors(conn, symbol)  # keep adj_factor continuous across download windows
    except Exception as exc:
        md.finish_load(conn, load_id, error=str(exc))
        raise
    md.finish_load(conn, load_id, count)
    return count


def fetch_fx(conn, start: str, end: str) -> int:
    rates = fx_source.fetch_rates_by_year("HKD", "CNY", start, end)
    return md.upsert_fx_rates(conn, "HKDCNY", rates, fx_source.SOURCE)


def import_actions(conn, csv_path: Path) -> int:
    grouped: dict[str, list[dict]] = {}
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped.setdefault(normalize_symbol(row["symbol"]), []).append(row)
    total = 0
    for symbol, rows in grouped.items():
        md.upsert_instrument(conn, symbol, symbol)
        total += md.upsert_corporate_actions(conn, symbol, rows, "csv")
        md.rebuild_adj_factors(conn, symbol)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch A-share / HK daily data (Tencent), HK board lots and HKD/CNY rates")
    parser.add_argument("--db", default=str(ROOT / "data_module" / "market_data.sqlite"))
    parser.add_argument("--symbols", nargs="*", default=[], help="e.g. 600519.SH 000001.SZ 00700.HK")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--board-lots", action="store_true", help="update HK board lots from the HKEX list")
    parser.add_argument("--fx", action="store_true", help="load HKD/CNY daily rates (for 港股通)")
    parser.add_argument("--import-actions", metavar="CSV", help="load corporate actions (dividends / bonus shares)")
    args = parser.parse_args()

    summary: dict[str, object] = {"bars": {}, "errors": {}}
    with md.connect(Path(args.db)) as conn:
        md.migrate(conn)
        for symbol in args.symbols:
            try:
                summary["bars"][normalize_symbol(symbol)] = fetch_symbol(conn, symbol, args.start, args.end)
                conn.commit()
            except Exception as exc:
                summary["errors"][symbol] = str(exc)
        if args.board_lots:
            try:
                summary["board_lots_updated"] = md.set_board_lots(conn, hkex.fetch_board_lots())
            except Exception as exc:
                summary["errors"]["board_lots"] = str(exc)
        if args.fx or any(normalize_symbol(s).endswith(".HK") for s in args.symbols):
            try:
                summary["fx_rates"] = fetch_fx(conn, args.start, args.end)
            except Exception as exc:
                summary["errors"]["fx"] = str(exc)
        if args.import_actions:
            summary["corporate_actions"] = import_actions(conn, Path(args.import_actions))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
