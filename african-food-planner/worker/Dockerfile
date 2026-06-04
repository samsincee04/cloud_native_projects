FROM python:3.11-slim

WORKDIR /app

# Install backend (provides `app.*` modules and deps)
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app
RUN pip install --no-cache-dir ./backend

# Copy worker code
COPY worker ./worker

ENV PYTHONPATH=/app

CMD ["python", "worker/run_jobs.py"]

