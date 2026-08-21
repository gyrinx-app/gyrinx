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
# front of every cold-started request.
#
# `|| true` is load-bearing. Gunicorn becomes PID 1 below, so this process ends
# up its child, and the arbiter's reaper calls waitpid(-1) and inspects the exit
# status *before* checking whether the pid was ever one of its workers. A
# non-zero exit is therefore logged as a phantom "Worker (pid:N) exited with
# code N", and — worse — exit codes 3 and 4 are the arbiter's WORKER_BOOT_ERROR
# and APP_LOAD_ERROR, which make it halt the whole container. Exiting 0 always
# keeps a failed provision to the log line it deserves.
#
# A failure here is survivable: the resources are almost always already in place
# from an earlier boot, and every later boot provisions again.
#
# The exception is the deploy that first introduces a task. Its topic does not
# exist yet, and for the few seconds before this finishes, enqueuing that task
# publishes to a topic that is not there. Enqueue is fire-and-forget, so that
# lands as a logged publish failure and the work is dropped rather than raised.
# Deploys adding a task should confirm provisioning finished before relying on
# it.
{ manage provision_tasks || true; } &
# 2 workers: the instances are 1 vCPU, so the pair shares a core (GIL) — which
#   the measured demand leaves ample room for (0.36 vCPU at p95). Two rather
#   than one for availability, not throughput: see --max-requests below.
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
# --limit-request-line: a print pick rides in the address, one parameter per
#   ticked model and weapon, so a big roster makes a long request line. Past
#   the limit gunicorn answers 414 itself — no Django, no page, no log line —
#   so the room is worth having rather than discovering.
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 2 --threads 20 --timeout 0 \
  --max-requests 1000 --max-requests-jitter 100 \
  --limit-request-line 8190 \
  --error-logfile /dev/stdout \
  "gyrinx.wsgi:application"
