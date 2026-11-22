FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install -e .

COPY config ./config
COPY scripts ./scripts
RUN mkdir -p logs reports

# ברירת מחדל: paper trading. ל-live החליפו את ה-CMD.
CMD ["pmmb", "paper", "--interval", "60"]
