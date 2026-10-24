FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/web_app/backend \
    DATABASE_URL=sqlite:////data/aquant_web_app.db \
    BACKUP_DIR=/data/backups

WORKDIR /app

COPY web_app/backend/requirements.txt /app/web_app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/web_app/backend/requirements.txt

# The API imports the research modules (engine, market rules, validator, data sources) from the repo root.
COPY backtest_module/*.py /app/backtest_module/
COPY backtest_module/output/price_breakout_demo /app/backtest_module/output/price_breakout_demo
COPY market_rules_module /app/market_rules_module
COPY data_module /app/data_module
COPY security_compliance_module /app/security_compliance_module
COPY strategy_module /app/strategy_module
COPY template_module/templates /app/template_module/templates
COPY web_app/backend/app /app/web_app/backend/app
COPY web_app/backend/alembic /app/web_app/backend/alembic
COPY web_app/backend/alembic.ini /app/web_app/backend/alembic.ini

COPY web_app/deploy/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod +x /usr/local/bin/backend-entrypoint.sh \
    && useradd --create-home --uid 10001 aquant && mkdir -p /data && chown -R aquant /data

WORKDIR /app/web_app/backend
VOLUME ["/data"]

# Starts as root only to chown the mounted volume, then runs the API as the unprivileged user.
# --proxy-headers makes the login throttle see the client IP behind the platform's proxy.
ENTRYPOINT ["/usr/local/bin/backend-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
