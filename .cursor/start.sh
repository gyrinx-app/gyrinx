#!/usr/bin/env bash
#
# Cloud Agent per-boot start script for Gyrinx.
#
# Brings PostgreSQL up on every boot (its data directory is captured in the
# build snapshot, so the migrated schema is already present) and returns once
# the server is accepting connections. The Django dev server itself runs as the
# "dev-server" terminal (see environment.json), so its logs stay visible.
#
# Anything added to this file belongs ABOVE the PostgreSQL readiness loop at the
# foot of it. That loop exits 0 as soon as the server answers, so work appended
# after it never runs.

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
# The directory holding it must not be world-writable: in a shared directory
# another process can pre-place a symlink at the destination and the write
# follows it, which is an arbitrary file overwrite running as this user. A
# private directory removes the exposure, and re-creating it with restrictive
# ownership on every boot repairs tampering rather than inheriting it.
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
#
# Nothing in this section may abort the script. Production access is an optional
# extra, and failing to configure it must not cost the environment its database.
# ---------------------------------------------------------------------------
WIF_CONFIG_DIR="/etc/gyrinx"
WIF_CONFIG_PATH="${WIF_CONFIG_DIR}/cursor-wif.json"

# Every path that does not write a fresh config discards the old one, so what is
# on disk always reflects the variable: rotating it to a different project, or
# withdrawing it, cannot leave an earlier boot's credentials in use. rm -f
# forgives a missing file but not a permission error, which would otherwise end
# the boot before PostgreSQL had started.
discard_config() { rm -f "$WIF_CONFIG_PATH" 2>/dev/null || true; }

if [ -z "${GCP_WIF_CONFIG:-}" ]; then
  discard_config
elif ! command -v jq >/dev/null 2>&1; then
  # Distinguished from a malformed variable so the reader is sent after the
  # right thing: jq arrives late in install.sh, so a partial build lands here.
  echo "jq is not installed; skipping credential config." >&2
  discard_config
elif ! printf '%s' "$GCP_WIF_CONFIG" | jq -e 'type == "object"' >/dev/null 2>&1; then
  # A typo fails closed rather than quietly leaving the previous credentials
  # usable.
  echo "GCP_WIF_CONFIG is set but is not a JSON object; skipping." >&2
  discard_config
elif ! sudo install -d -m 700 -o "$(id -u)" -g "$(id -g)" "$WIF_CONFIG_DIR" 2>/dev/null; then
  echo "Could not create ${WIF_CONFIG_DIR}; skipping credential config." >&2
  discard_config
elif ! WIF_TMP=$(mktemp "${WIF_CONFIG_DIR}/.cursor-wif.XXXXXX" 2>/dev/null); then
  echo "Could not create a temporary file in ${WIF_CONFIG_DIR}; skipping credential config." >&2
  discard_config
else
  # Written to a fresh file inside the private directory and renamed into place.
  # rename(2) replaces a symlink at the destination rather than following it, so
  # there is no window in which the final path can be redirected, and mktemp
  # creates at mode 600 to begin with.
  if { printf '%s' "$GCP_WIF_CONFIG" > "$WIF_TMP" 2>/dev/null \
    && chmod 600 "$WIF_TMP" 2>/dev/null \
    && mv -f "$WIF_TMP" "$WIF_CONFIG_PATH" 2>/dev/null; }; then
    echo "Wrote Google credential config to ${WIF_CONFIG_PATH}."
  else
    rm -f "$WIF_TMP" 2>/dev/null || true
    echo "Could not write ${WIF_CONFIG_PATH}; skipping credential config." >&2
    discard_config
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
