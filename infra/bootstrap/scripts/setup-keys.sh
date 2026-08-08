#!/usr/bin/env bash
# Generate (or refresh) the GCP service account JSON key for a Spacelift
# stack, and place it where the bootstrap module expects to read it.
#
# Why:
#   The Spacelift mounted_file resource calls filebase64() on a JSON key
#   stored on the operator's disk. We never put the key in TF state or in
#   the repo — it lives in ~/.config/gyrinx/spacelift-keys/ and is
#   symlinked into infra/bootstrap/keys/.
#
# Usage:
#   scripts/setup-keys.sh <env>           # one env, e.g. "staging"
#   scripts/setup-keys.sh staging prod    # multiple
#
# Run from infra/bootstrap/. Assumes:
#   - The Spacelift SA already exists in GCP for each env (created by
#     a prior `terraform apply` of this module without the
#     spacelift_mounted_file resources — or with create_project=false
#     and SAs created out of band).

set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <env> [<env>...]" >&2
  exit 2
fi

KEYS_DIR="$HOME/.config/gyrinx/spacelift-keys"
LINK_TARGET="$(cd "$(dirname "$0")/.." && pwd)/keys"

mkdir -p "$KEYS_DIR"
chmod 700 "$KEYS_DIR"

# Symlink infra/bootstrap/keys/ -> ~/.config/gyrinx/spacelift-keys/
if [[ ! -L "$LINK_TARGET" ]]; then
  if [[ -d "$LINK_TARGET" ]]; then
    echo "error: $LINK_TARGET exists and is not a symlink; move its contents to $KEYS_DIR and remove it." >&2
    exit 1
  fi
  ln -s "$KEYS_DIR" "$LINK_TARGET"
  echo "linked $LINK_TARGET -> $KEYS_DIR"
fi

# Map env -> project ID. Keep this list in sync with terraform.tfvars.
declare -A PROJECT_OF
PROJECT_OF[staging]="gyrinx-staging"
PROJECT_OF[prod]="windy-ellipse-440618-p9"

for env in "$@"; do
  project_id="${PROJECT_OF[$env]:-}"
  if [[ -z "$project_id" ]]; then
    echo "error: unknown env '$env' (expected one of: ${!PROJECT_OF[*]})" >&2
    exit 1
  fi

  sa_email="spacelift@${project_id}.iam.gserviceaccount.com"
  key_path="$KEYS_DIR/spacelift-${env}.json"

  if [[ -f "$key_path" ]]; then
    echo "$env: $key_path already exists, skipping. Delete it first if you want to rotate."
    continue
  fi

  echo "$env: creating key for $sa_email -> $key_path"
  gcloud iam service-accounts keys create "$key_path" \
    --iam-account="$sa_email" \
    --project="$project_id"
  chmod 600 "$key_path"
done

echo ""
echo "Done. Now re-run terraform apply in infra/bootstrap/ to upload the keys to Spacelift."
