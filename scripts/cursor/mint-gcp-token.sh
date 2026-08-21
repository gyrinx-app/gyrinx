#!/usr/bin/env bash
# Google external_account executable-sourced credential for Cursor Cloud Agents.
# Mints a five-minute OIDC JWT from the local Cursor agent socket and prints the
# JSON contract Google's auth libraries expect on stdout.
#
# Contract sources:
#   Cursor: https://cursor.com/docs/cloud-agent/identity
#   Google: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers
#
# Requires: curl, jq. Set GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1 in the env.
#
# errexit is deliberately NOT enabled. The contract is to exit 0 having printed
# a JSON document in every circumstance, so a stray non-zero status from any
# command must not terminate the script; each step is checked explicitly instead.
set -uo pipefail

SOCKET="${CURSOR_AGENT_SOCKET:-/run/cursor/api.sock}"
AUD="${GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE:-}"
OUT="${GOOGLE_EXTERNAL_ACCOUNT_OUTPUT_FILE:-}"

# The retry budget must finish inside the executable timeout the credential
# config allows, or the process is killed part-way through and the failure
# document never reaches stdout -- the very outcome exiting 0 exists to avoid.
# Worst case is ATTEMPTS x MAX_TIME plus the waits between them: eleven seconds,
# against a timeout the config sets at fifteen. Raise the two together, and keep
# the margin: the worst case only arrives when the socket hangs rather than
# refusing, which is exactly when the failure document matters most.
ATTEMPTS=3
MAX_TIME=3
RETRY_WAIT=1

# The auth library reads stdout as JSON, so a failure is reported as a document
# rather than an exit status; a non-zero exit yields a far less useful error.
# The code field mirrors the HTTP status where there is one.
emit_failure() {
  local message="$1" code="${2:-401}"
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg m "$message" --arg c "$code" \
      '{version:1, success:false, code:$c, message:$m}'
  else
    printf '{"version":1,"success":false,"code":"401","message":"jq is not installed"}\n'
  fi
  exit 0
}

# A response body is quoted back only for statuses that cannot be carrying a
# token, so an unexpected success never puts a JWT into an error message, an
# exception, or a log.
describe_body() {
  case "$1" in
    000 | 4?? | 5??) printf '%.200s' "$2" ;;
    *) printf '(body withheld: a %s response may carry a token)' "$1" ;;
  esac
}

command -v jq >/dev/null 2>&1 || emit_failure "jq is not installed"
command -v curl >/dev/null 2>&1 || emit_failure "curl is not installed"
[ -n "$AUD" ] || emit_failure "GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE is not set"

body=$(jq -nc --arg aud "$AUD" '{aud: $aud}') \
  || emit_failure "could not build the mint request body"

code=""
payload=""
attempt=0
while [ "$attempt" -lt "$ATTEMPTS" ]; do
  attempt=$((attempt + 1))

  # The socket can be absent briefly after boot, so a connection failure is
  # retried rather than treated as fatal.
  if resp=$(curl -sS --max-time "$MAX_TIME" -w $'\n%{http_code}' \
    --unix-socket "$SOCKET" \
    -H 'Content-Type: application/json' \
    -d "$body" \
    http://cursor-agent/v1/tokens/oidc 2>/dev/null); then
    code=$(printf '%s' "$resp" | tail -n1)
    payload=$(printf '%s' "$resp" | sed '$d')
  else
    code="000"
    payload="could not connect to ${SOCKET}"
  fi

  case "$code" in
    200) break ;;
    # Cursor documents 403 as fatal: this run is not allowed to mint at all.
    403) emit_failure "cursor refused the mint: $(describe_body "$code" "$payload")" "403" ;;
    000 | 429 | 500 | 502 | 503 | 504)
      if [ "$attempt" -ge "$ATTEMPTS" ]; then
        emit_failure "cursor mint failed after ${ATTEMPTS} attempts (last: ${code} $(describe_body "$code" "$payload"))" "$code"
      fi
      sleep "$RETRY_WAIT"
      ;;
    *) emit_failure "cursor mint failed: $(describe_body "$code" "$payload")" "$code" ;;
  esac
done

[ "$code" = "200" ] || emit_failure "cursor mint did not succeed (last: ${code})" "$code"

token=$(printf '%s' "$payload" | jq -r '.token // empty' 2>/dev/null) \
  || emit_failure "mint response could not be read as a JSON object"
expiry=$(printf '%s' "$payload" | jq -r '.expires_at // empty' 2>/dev/null) \
  || emit_failure "mint response could not be read as a JSON object"

[ -n "$token" ] || emit_failure "mint response carried no token"

# Guards --argjson below, which rejects anything that is not a JSON number. It
# also accepts an expiry delivered as a string, since jq -r has already removed
# the quotes.
case "$expiry" in
  '' | *[!0-9]*) emit_failure "mint response carried no usable expiry" ;;
esac

# Google wants an absolute time in seconds. A relative lifetime would read as a
# 1970 expiry and a value in milliseconds would cache a token long past its
# death, and neither announces itself -- so both are rejected here rather than
# left to surface as an inexplicable authentication failure later.
now=$(date +%s)
if [ "$expiry" -le "$now" ]; then
  emit_failure "mint response expiry is not in the future; expected epoch seconds"
elif [ "$expiry" -gt $((now + 86400)) ]; then
  emit_failure "mint response expiry is implausibly distant; expected epoch seconds"
fi

result=$(jq -nc --arg t "$token" --argjson e "$expiry" \
  '{version:1, success:true, token_type:"urn:ietf:params:oauth:token-type:id_token", id_token:$t, expiration_time:$e}') \
  || emit_failure "could not build the credential document"

# Cache for the library. Cursor allows 30 mints a minute per machine and tokens
# last five minutes, so letting it reuse a live token matters.
#
# Best effort throughout: a token in hand must reach stdout even if it cannot be
# stored. The file is created by mktemp beside its destination and renamed into
# place, because the nominated path can sit in a shared directory where another
# process may have pre-placed a symlink; rename(2) replaces such a link rather
# than writing through it, and mktemp opens at mode 600 to begin with.
case "$OUT" in
  '') ;;
  /*) ;;
  # A relative path would land in whatever directory the library happened to
  # invoke this from, which is nobody's intent.
  *)
    echo "warning: ignoring a relative cache path: ${OUT}" >&2
    OUT=""
    ;;
esac

if [ -n "$OUT" ]; then
  if cache_tmp=$(mktemp "$(dirname "$OUT")/.cursor-gcp-token.XXXXXX" 2>/dev/null); then
    if ! { printf '%s' "$result" > "$cache_tmp" 2>/dev/null \
      && chmod 600 "$cache_tmp" 2>/dev/null \
      && mv -f "$cache_tmp" "$OUT" 2>/dev/null; }; then
      rm -f "$cache_tmp" 2>/dev/null
      echo "warning: could not cache the token at ${OUT}" >&2
    fi
  else
    echo "warning: could not create a cache file beside ${OUT}" >&2
  fi
fi

printf '%s\n' "$result"
exit 0
