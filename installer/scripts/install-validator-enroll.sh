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
for command_name in gpg awk sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || fail \
    "Required validator-tool verification command is unavailable: $command_name"
done
for file in install-roko-validator-enroll.sh SHA256SUMS SHA256SUMS.asc roko-release-signing-key.asc; do
  curl --fail --location --silent --show-error "$release_base/$file" --output "$task_dir/$file"
done
expected_fingerprint="62297562B1C7053088F405DB0117DAAA677A5BF2"
key_home="$task_dir/key-inspect"
install -d -m 0700 "$key_home"
actual_fingerprint="$(GNUPGHOME="$key_home" gpg --batch --with-colons \
  --import-options show-only --import "$task_dir/roko-release-signing-key.asc" 2>/dev/null \
  | awk -F: '$1 == "fpr" {print toupper($10); exit}')"
[[ "$actual_fingerprint" == "$expected_fingerprint" ]] || fail \
  "Validator-tool release key fingerprint mismatch. Expected $expected_fingerprint."
gpg_home="$task_dir/gnupg"
install -d -m 0700 "$gpg_home"
GNUPGHOME="$gpg_home" gpg --batch --quiet --import "$task_dir/roko-release-signing-key.asc"
GNUPGHOME="$gpg_home" gpg --batch --verify "$task_dir/SHA256SUMS.asc" "$task_dir/SHA256SUMS"
installer_line="$(awk '$2 == "install-roko-validator-enroll.sh" || $2 == "*install-roko-validator-enroll.sh" {print; exit}' "$task_dir/SHA256SUMS")"
[[ -n "$installer_line" ]] || fail "Signed validator-tool manifest omits its installer."
(cd "$task_dir" && printf '%s\n' "$installer_line" | sha256sum --check --strict)
bash -n "$task_dir/install-roko-validator-enroll.sh"
as_root bash "$task_dir/install-roko-validator-enroll.sh" --release-base "$release_base"

resolved="$(command -v roko-validator-enroll || true)"
[[ -n "$resolved" && -x "$resolved" ]] || fail \
  "roko-validator-enroll was not installed. Download and verify it at $release_base/"
version_output="$(roko-validator-enroll --version 2>&1)" || fail \
  "roko-validator-enroll cannot run. Reinstall from $release_base/"
log "Validator enrollment command: $resolved"
log "Validator enrollment version: $version_output"
