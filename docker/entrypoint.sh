#!/bin/sh

set -e

# collectstatic is NOT here: it runs at image build time (see Dockerfile). Its
# output is identical for every container started from a given image, so doing
# it per boot re-hashed and re-compressed ~1200 files on the critical path of
# the first request after a scale-from-zero.
manage migrate
manage ensuresuperuser --no-input

# Pub/Sub topics/subscriptions/scheduler jobs. Backgrounded deliberately: it is
# idempotent bookkeeping that no request depends on, and running it inline (as
# TasksConfig.ready() used to) put ~120s of blocking Pub/Sub admin calls in
# front of every cold-started request. Gunicorn becomes PID 1 below and reaps it.
manage provision_tasks &
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
