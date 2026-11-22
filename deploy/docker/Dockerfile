# תמונה קטנה, משתמש לא-שורש, בריאות מוגדרת.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PMMB_STATE_DIR=/app/state
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e . \
    && useradd -m -u 10001 pmmb && mkdir -p /app/logs /app/reports /app/state \
    && chown -R pmmb:pmmb /app

USER pmmb
EXPOSE 8787
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
  CMD pmmb status --json --max-age 300 > /dev/null || exit 1

CMD ["pmmb", "paper", "--interval", "60"]
