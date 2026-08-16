#!/usr/bin/env bash
#
# Cloud Agent per-boot start script for Gyrinx.
#
# Brings PostgreSQL up on every boot (its data directory is captured in the
# build snapshot, so the migrated schema is already present) and returns once
# the server is accepting connections. The Django dev server itself runs as the
# "dev-server" terminal (see environment.json), so its logs stay visible.

set -euo pipefail

sudo pg_ctlcluster 16 main start 2>/dev/null \
  || sudo service postgresql start 2>/dev/null \
  || true

for _ in $(seq 1 30); do
  if pg_isready -q; then
    echo "PostgreSQL is ready."
    exit 0
  fi
  sleep 1
done

echo "PostgreSQL did not become ready within 30s" >&2
exit 1
