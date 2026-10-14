#!/bin/sh
# Production process for Render. Do not use `python run.py` there.
set -eu
cd "$(dirname "$0")/.."

# Render injects GUNICORN_CMD_ARGS="--preload --access-logfile - --bind=0.0.0.0:10000".
# --preload opens SQLite in the master, then forks a worker that inherits a dead
# connection. The hardcoded bind also ignores a custom PORT. This script owns both.
unset GUNICORN_CMD_ARGS

port="${PORT:-10000}"
exec gunicorn wsgi:app \
  --bind "0.0.0.0:${port}" \
  --workers 1 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
