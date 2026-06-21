# AQuant Studio Web App

This directory is the V2 online web application structure for AQuant Studio.

Stage 1 goal:

- Create a real web app project layout.
- Separate backend and frontend code.
- Prepare API, service, schema, task, and database boundaries.
- Keep the existing MVP modules intact while creating a clean migration target.

## Structure

```text
web_app/
  backend/
    app/
      api/
      core/
      models/
      schemas/
      services/
      tasks/
      main.py
    tests/
    pyproject.toml
    .env.example
  frontend/
    src/
    public/
    package.json
    index.html
  docs/
  scripts/
```

## Stage 1 Status

This is an engineering skeleton. It is not yet the full online product.

The first backend endpoints are:

```text
GET /
GET /health
GET /api/v1/security/status
GET /api/v1/templates
GET /api/v1/templates/{template_id}
POST /api/v1/strategies/validate
POST /api/v1/backtests
GET /api/v1/backtests/{backtest_id}
```

The frontend currently renders a static shell that points to the future product areas.

## Next Stage

Stage 2 wraps the existing MVP modules as synchronous FastAPI endpoints. Stage 3 will introduce the database layer.
