#!/bin/sh
set -e

echo "Starting Temporal dev server..."

temporal server start-dev \
  --ip 0.0.0.0 \
  --db-filename /tmp/temporal.db \
  > /tmp/temporal.log 2>&1 &

echo "Waiting for Temporal..."
sleep 5

echo "Starting Temporal worker..."

python -m app.worker \
  > /tmp/worker.log 2>&1 &

echo "Starting FastAPI..."

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-10000}"