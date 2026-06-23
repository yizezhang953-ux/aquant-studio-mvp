FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY web_app/backend/pyproject.toml /app/web_app/backend/pyproject.toml
COPY web_app/backend/app /app/web_app/backend/app
COPY web_app/backend/tests /app/web_app/backend/tests
COPY backtest_module /app/backtest_module
COPY data_module /app/data_module
COPY security_compliance_module /app/security_compliance_module
COPY strategy_module /app/strategy_module
COPY template_module /app/template_module

RUN pip install --no-cache-dir -e /app/web_app/backend

WORKDIR /app/web_app/backend

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
