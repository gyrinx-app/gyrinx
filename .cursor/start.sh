#!/usr/bin/env bash
#
# Cloud Agent per-boot start script for Gyrinx.
#
# Brings PostgreSQL up on every boot (its data directory is captured in the
# build snapshot, so the migrated schema is already present) and returns once
# the server is accepting connections. The Django dev server itself runs as the
# "dev-server" terminal (see environment.json), so its logs stay visible.

set -euo pipefail

# ---------------------------------------------------------------------------
# Read-only production database credentials.
#
# GCP_WIF_CONFIG holds the external_account configuration as JSON. It is
# supplied as a Cursor environment variable rather than committed, because this
# repository is public and the config names the Google Cloud project. Writing it
# here rather than in install.sh keeps it out of the build snapshot.
#
# The file lands outside the workspace so it never appears in git status.
# GOOGLE_APPLICATION_CREDENTIALS must point at this same path, and
# GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES must be 1; both are set as Cursor
# environment variables, because exports from this script do not reach the
# agent's own shell.
#
# An unset variable is the normal case: agents that do not need production
# access simply skip this.
# ---------------------------------------------------------------------------
WIF_CONFIG_PATH="${HOME}/.gcp/cursor-wif.json"
if [ -n "${GCP_WIF_CONFIG:-}" ]; then
  if printf '%s' "$GCP_WIF_CONFIG" | jq -e 'type == "object"' >/dev/null 2>&1; then
    mkdir -p "$(dirname "$WIF_CONFIG_PATH")"
    # Subshell so the restrictive umask applies to the file at creation rather
    # than leaving it briefly world-readable before a chmod.
    ( umask 077; printf '%s' "$GCP_WIF_CONFIG" > "$WIF_CONFIG_PATH" )
    echo "Wrote Google credential config to ${WIF_CONFIG_PATH}."
  else
    # Warn rather than exit: a malformed variable should not stop the dev
    # server from coming up.
    echo "GCP_WIF_CONFIG is set but is not a JSON object; skipping." >&2
  fi
fi

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
