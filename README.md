# AQuant Studio MVP

AQuant Studio is a quantitative strategy research platform MVP for **China A-shares, Hong Kong stocks and Southbound Stock Connect (港股通)**.

| `market` | Account | Rules applied in backtests |
|---|---|---|
| `a_share` | CNY | 100-share lots (STAR 200+), T+1, board price limits, stamp duty by date, minimum commission, holding-period dividend tax |
| `hk_stock` | HKD | per-stock board lots, T+0, no daily limit, HK stamp duty and levies |
| `hk_connect` | CNY | HK rules + daily HKD→CNY conversion, trades only when both HK and the mainland are open, 20% dividend withholding |

See [CHANGES-v0.2-multi-market.md](CHANGES-v0.2-multi-market.md) for what changed in v0.2 (Chinese).

## Quick start (Windows)

Double-click **`start.bat`** in the repository root. It finds Python 3.11+, creates `web_app/backend/.venv`, installs
the backend requirements on the first run (falling back to the Tsinghua PyPI mirror), starts the web app and opens
<http://127.0.0.1:8000/>. Node.js is not needed: the backend serves the pre-built frontend in `web_app/frontend/dist`.

Before starting, `start.bat` pulls the latest version with `git pull --ff-only` (using Git on PATH or the copy bundled
with GitHub Desktop) and restarts itself if anything changed. It never overwrites local edits; if the pull fails (offline,
conflicting local change) it starts the current version. Create `web_app/backend/runtime/no_auto_update.txt` to turn it off.

The first account you register locally becomes the administrator (needed to sync market data under 行情数据 → 同步真实日线).
On macOS/Linux: `cd web_app/backend && pip install -r requirements.txt && uvicorn app.main:app`, then open <http://127.0.0.1:8000/>.

After changing `web_app/frontend/src`, rebuild with `cd web_app/frontend && pnpm install && pnpm build` and commit `dist/`.

It includes:

- Product requirements and prototype
- Market data module (A-share + HK) with a free real-data loader (Tencent quotes, HKEX board lots, ECB HKD/CNY)
- Market rules for A-share / HK / 港股通 (`market_rules_module`)
- Strategy DSL and validator
- Backtest engine
- Strategy template library
- Backtest visualization
- Parameter optimization with out-of-sample validation (holdout / walk-forward)
- Paper trading simulation
- Sandbox trading gateway
- Security and compliance checks
- MVP release homepage

## Open The MVP

Open:

```text
release_module/index.html
```

For GitHub Pages, the root `index.html` redirects to:

```text
release_module/index.html
```

## Status

This project is a research and sandbox MVP.

Live trading is explicitly blocked:

```text
blocked_for_live_trading
```

It does not connect to a real broker, does not place real orders, and does not provide investment advice.

## Main Entry Points

| Module | Entry |
|---|---|
| MVP homepage | `release_module/index.html` |
| Product prototype | `prototype/index.html` |
| Backtest report | `visualization_module/output/price_breakout_report.html` |
| Parameter optimization | `optimization_module/output/price_breakout_grid/ranking.html` |
| Paper trading report | `simulation_module/output/price_breakout_paper/paper_trading_report.html` |
| Security report | `security_compliance_module/output/security_compliance_report.html` |
| Live trading stage 1 delivery | `trading_gateway_module/live-trading-stage-1-delivery.md` |
| Market rules stage 2 delivery | `market_rules_module/market-rules-stage-2-delivery.md` |
| Risk gateway stage 3 delivery | `trading_gateway_module/risk-gateway-stage-3-delivery.md` |
| Event-driven paper stage 4 delivery | `simulation_module/event-driven-paper-stage-4-delivery.md` |
| Broker adapter stage 5 delivery | `broker_adapter_module/broker-adapter-stage-5-delivery.md` |
| Read-only account stage 6 delivery | `broker_adapter_module/read-only-account-stage-6-delivery.md` |
| Shadow trading stage 7 delivery | `shadow_trading_module/shadow-trading-stage-7-delivery.md` |
| Manual confirmation stage 8 delivery | `manual_confirmation_module/manual-confirmation-stage-8-delivery.md` |
| Limited auto stage 9 delivery | `automation_controls_module/limited-auto-stage-9-delivery.md` |
| Monitoring stage 10 delivery | `monitoring_module/monitoring-stage-10-delivery.md` |
| Audit stage 11 delivery | `audit_module/audit-stage-11-delivery.md` |
| Final readiness stage 12 delivery | `live_readiness_module/final-readiness-stage-12-delivery.md` |

## Bulk sync and live quotes

- 「行情数据」: paste many codes at once (`600519 000001 700.hk`, spaces / commas / new lines) or press 「更新全部」. The batch runs in the background, downloading 4 stocks at a time; stocks already stored are only topped up from their last bar. 「每日信号」 and 「批量回测」 use the same batch sync.
- 「实时价格」 on the stock list shows Tencent live quotes (about 3 s delayed, refreshed every 5 s during trading hours). 「每日信号」→「盘中预判」 treats the current price as today's close to preview the signals before the close.
- Tencent's endpoints are free and unofficial: fine for a personal watchlist, not for scraping the whole market every few seconds.

## Daily automation (每日自动运行)

「每日信号」→「收盘后自动运行」 runs a job on every A-share / HK trading day at the chosen Beijing time (default 16:30):

1. syncs the latest daily bars for every stock in your paper accounts (admins only; 400 days of history the first time) and the 恒指 / 沪深300 indices;
2. replays every paper account and lists the orders due at the next open;
3. pushes the summary to PushPlus, Server酱, or an 企业微信 / 钉钉 / 飞书 group-bot webhook.

It only sends messages; it never places orders. The scheduler lives inside the app, so keep the start.bat window open; if the computer was off at the set time, the job runs as soon as the app starts that day. Set `AUTOMATION_SCHEDULER_ENABLED=false` to turn the background thread off.

## Live Trading Roadmap

Stage 1 has started the controlled live-trading upgrade path by adding an OMS order lifecycle and live-trading policy gate.
Stage 2 adds a configurable A-share and Hong Kong stock market rules module.
Stage 3 adds runtime risk controls before broker adapter submission.
Stage 4 adds an event-driven paper trader with partial fills and cancel events.
Stage 5 adds a broker adapter interface and moves sandbox broker behavior behind it.
Stage 6 adds a read-only broker adapter skeleton and account snapshot sync.
Stage 7 adds shadow trading reports that never submit orders.
Stage 8 adds a manual confirmation workflow before any approved order can be exported.
Stage 9 adds a limited automation guard that creates candidates without live submission.
Stage 10 adds monitoring summaries and alert status.
Stage 11 adds an audit manifest with file hashes for key live-readiness artifacts.
Stage 12 adds a final readiness check that keeps live trading blocked until external confirmations are complete.

Current safety state remains:

```text
live_trading_enabled = false
allow_real_broker_submit = false
```

The system can route strategy orders through the gateway and sandbox adapter, but it still cannot submit real broker orders.

## V2 Web App Structure

The online backend application work starts in:

```text
web_app/
```

It contains a FastAPI backend (Alembic migrations, SQLite or PostgreSQL) and a React/Vite frontend. See [web_app/README.md](web_app/README.md).

## Real Data

The bundled sample database only has 5 A-share daily bars per symbol. Load real history on a machine with internet access:

```bash
python data_module/fetch_market_data.py --symbols 600519.SH 000001.SZ 00700.HK 00168.HK --start 2016-01-01 --board-lots --fx
python backtest_module/backtest_engine.py template_module/templates/hk_connect_ma_trend.json --output-dir backtest_module/output/hk_connect_demo
```

## Tests

```bash
python -m pytest tests -q                    # market rules, engine, data sources, optimizer
cd web_app/backend && python -m pytest -q    # API (set TEST_DATABASE_URL to run on PostgreSQL)
```

## Run Demo Check

```powershell
python release_module/run_mvp_demo.py
```

If you are using the Codex bundled Python on this machine:

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' release_module\run_mvp_demo.py
```
