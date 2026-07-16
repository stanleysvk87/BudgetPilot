FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUDGETPILOT_HOME=/var/lib/budgetpilot \
    BUDGETPILOT_HOST=0.0.0.0 \
    BUDGETPILOT_PORT=8765

WORKDIR /app

RUN addgroup --system budgetpilot \
    && adduser --system --ingroup budgetpilot --home /app budgetpilot

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /var/lib/budgetpilot/data /var/lib/budgetpilot/backups \
    && chown -R budgetpilot:budgetpilot /app /var/lib/budgetpilot

USER budgetpilot
EXPOSE 8765
VOLUME ["/var/lib/budgetpilot"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=3).close()"

CMD ["sh", "-c", "exec gunicorn --bind ${BUDGETPILOT_HOST:-0.0.0.0}:${BUDGETPILOT_PORT:-8765} --workers ${BUDGETPILOT_WORKERS:-2} --timeout 60 budgetpilot_web:app"]
