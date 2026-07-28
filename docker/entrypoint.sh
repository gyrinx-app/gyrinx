#!/bin/sh

set -e

manage collectstatic --noinput
manage migrate
manage ensuresuperuser --no-input
# 2 workers: one busy core each on the 2-vCPU Cloud Run instances (GIL).
# 20 threads each: 2 × 20 = 40 matches the service's containerConcurrency.
# --timeout 0: gthread heartbeats are per-worker (not per-request), so the
#   default 30s would never kill a slow page — but Cloud Run throttles CPU
#   between requests, stalling heartbeats, and a finite timeout then kills
#   healthy workers spuriously on wake. Trade-off: a truly wedged worker is
#   never auto-restarted (Cloud Run routes away from failing instances).
# --max-requests: recycle workers periodically as a leak backstop
#   (2 workers ensure one always serves during a graceful recycle).
# --error-logfile /dev/stdout: gunicorn logs to stderr by default and Cloud
#   Run labels stderr ERROR, which would page on every routine boot line.
# No access log: Cloud Run request logs already cover it.
# The DB pool in gyrinx/settings_prod.py is sized per worker process —
# change the worker count and the pool max_size together.
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 2 --threads 20 --timeout 0 \
  --max-requests 1000 --max-requests-jitter 100 \
  --error-logfile /dev/stdout \
  "gyrinx.wsgi:application"
