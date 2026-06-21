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
