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
# The path is fixed and absolute rather than derived from $HOME. It has to be
# repeated verbatim in GOOGLE_APPLICATION_CREDENTIALS, and a path that depends
# on which user the agent runs as is a silent mismatch waiting to happen.
#
# It is NOT in /tmp. A shared, world-writable directory lets any other process
# on the machine pre-place a symlink at the destination, in which case the write
# lands wherever that link points -- an arbitrary file overwrite running as this
# user. A private directory removes the exposure entirely; the directory is
# re-created with restrictive ownership on every boot, so tampering between runs
# is repaired rather than inherited.
#
# GOOGLE_APPLICATION_CREDENTIALS must name this same path and
# GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES must be 1; both are set as Cursor
# environment variables, because exports from this script do not reach the
# agent's own shell.
#
# An unset variable is the normal case: agents that do not need production
# access simply skip this. Whatever the outcome, what is on disk ends up
# reflecting the variable, so withdrawing the variable withdraws the access
# rather than leaving an earlier boot's config in place.
# ---------------------------------------------------------------------------
WIF_CONFIG_DIR="/etc/gyrinx"
WIF_CONFIG_PATH="${WIF_CONFIG_DIR}/cursor-wif.json"

if [ -z "${GCP_WIF_CONFIG:-}" ]; then
  rm -f "$WIF_CONFIG_PATH"
else
  if ! printf '%s' "$GCP_WIF_CONFIG" | jq -e 'type == "object"' >/dev/null 2>&1; then
    # Warn rather than exit: a malformed variable should not stop the dev
    # server from coming up. The old config goes anyway, so a typo fails closed
    # instead of quietly leaving the previous credentials usable.
    echo "GCP_WIF_CONFIG is set but is not a JSON object; skipping." >&2
    rm -f "$WIF_CONFIG_PATH"
  elif ! sudo install -d -m 700 -o "$(id -u)" -g "$(id -g)" "$WIF_CONFIG_DIR" 2>/dev/null; then
    echo "Could not create ${WIF_CONFIG_DIR}; skipping credential config." >&2
  else
    # Written to a fresh file inside the private directory and renamed into
    # place. rename(2) replaces a symlink at the destination rather than
    # following it, so there is no window in which the final path can be
    # redirected. mktemp creates at mode 600 to begin with.
    WIF_TMP=$(mktemp "${WIF_CONFIG_DIR}/.cursor-wif.XXXXXX")
    printf '%s' "$GCP_WIF_CONFIG" > "$WIF_TMP"
    chmod 600 "$WIF_TMP"
    mv -f "$WIF_TMP" "$WIF_CONFIG_PATH"
    echo "Wrote Google credential config to ${WIF_CONFIG_PATH}."
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
