#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[[ "${NODE_ROLE:-}" == validator-candidate ]] || {
  log "Active-authority manifest step skipped for role ${NODE_ROLE:-unknown}."
  exit 0
}

require_command curl
require_command gpg
require_command python3
manifest_url="${ROKO_AUTHORITY_MANIFEST_URL:-https://nodes.roko.network/authority-peers.json}"
output="${ROKO_AUTHORITY_MANIFEST_PATH:-/etc/roko/authority-peers.json}"
task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT

curl --fail --location --silent --show-error "$manifest_url" --output "$task_dir/authority-peers.json"
curl --fail --location --silent --show-error "$manifest_url.asc" --output "$task_dir/authority-peers.json.asc"
require_command roko-authority-peers
roko-authority-peers \
  --manifest "$task_dir/authority-peers.json" \
  --signature "$task_dir/authority-peers.json.asc" \
  --output "$task_dir/verified.json"
as_root install -d -o root -g root -m 0755 "$(dirname "$output")"
as_root install -o root -g root -m 0644 "$task_dir/verified.json" "$output"
log "Installed signed active-authority transport contract: $output"
