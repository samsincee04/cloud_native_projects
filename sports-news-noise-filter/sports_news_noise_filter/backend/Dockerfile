FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY app /app/app

RUN pip install --no-cache-dir pip setuptools wheel \
    && pip install --no-cache-dir \
    "fastapi>=0.104.0" \
    "uvicorn[standard]>=0.24.0" \
    "sqlalchemy>=2.0.0" \
    "psycopg[binary]>=3.1.0" \
    "python-dotenv>=1.0.0"

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
