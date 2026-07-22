# AQuant Studio MVP

AQuant Studio is an A-share quantitative strategy research platform MVP.

It includes:

- Product requirements and prototype
- A-share sample market data module
- Strategy DSL and validator
- Backtest engine
- Strategy template library
- Backtest visualization
- Parameter optimization
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

It contains a FastAPI backend skeleton and a React/Vite frontend skeleton.

## Run Demo Check

```powershell
python release_module/run_mvp_demo.py
```

If you are using the Codex bundled Python on this machine:

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' release_module\run_mvp_demo.py
```
