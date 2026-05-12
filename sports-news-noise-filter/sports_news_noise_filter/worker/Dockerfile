FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/worker-requirements.txt

# Layout: /app/docs, /app/backend/app (for worker SQLAlchemy report), /app/worker
COPY docs /app/docs
COPY backend/app /app/backend/app
COPY worker /app/worker

WORKDIR /app/worker
ENV PYTHONPATH=/app/backend

CMD ["python", "run_once.py"]
