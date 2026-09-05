#!/usr/bin/env bash
set -euo pipefail
# Resolved relative to this script at runtime.
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

validate_common_params
[[ "$NODE_ROLE" == validator-candidate ]] || {
  log "Validator enrollment CLI is not required for role $NODE_ROLE."
  exit 0
}

release_base="${ROKO_VALIDATOR_ENROLL_RELEASE_BASE:-https://downloads.roko.network/validator-tools/current}"
task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT
for file in install-roko-validator-enroll.sh install-roko-validator-enroll.sh.sha256; do
  curl --fail --location --silent --show-error "$release_base/$file" --output "$task_dir/$file"
done
(
  cd "$task_dir"
  sha256sum --check --strict install-roko-validator-enroll.sh.sha256
)
bash -n "$task_dir/install-roko-validator-enroll.sh"
as_root bash "$task_dir/install-roko-validator-enroll.sh" --release-base "$release_base"

resolved="$(command -v roko-validator-enroll || true)"
[[ -n "$resolved" && -x "$resolved" ]] || fail \
  "roko-validator-enroll was not installed. Download and verify it at $release_base/"
version_output="$(roko-validator-enroll --version 2>&1)" || fail \
  "roko-validator-enroll cannot run. Reinstall from $release_base/"
log "Validator enrollment command: $resolved"
log "Validator enrollment version: $version_output"
