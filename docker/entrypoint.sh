#!/bin/sh

set -e

manage collectstatic --noinput
manage migrate
manage ensuresuperuser --no-input
# 2 workers: one busy core each on the 2-vCPU Cloud Run instances (GIL).
# 20 threads each: 2 × 20 = 40 matches the service's containerConcurrency.
# --timeout 0: Cloud Run enforces the request timeout; gunicorn's own
# 30s default would kill workers mid-request on slow pages.
# The DB pool in gyrinx/settings_prod.py is sized per worker process —
# change the worker count and the pool max_size together.
exec gunicorn --bind "0.0.0.0:$PORT" --workers 2 --threads 20 --timeout 0 "gyrinx.wsgi:application"
