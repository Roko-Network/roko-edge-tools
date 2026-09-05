#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT
gpg_home="$task_dir/gnupg"
install -d -m 0700 "$gpg_home"
GNUPGHOME="$gpg_home" gpg --batch --passphrase '' --quick-generate-key \
  'ROKO package fixture <fixture@example.invalid>' ed25519 sign 0 >/dev/null 2>&1
fingerprint="$(GNUPGHOME="$gpg_home" gpg --batch --with-colons --list-secret-keys | awk -F: '$1 == "fpr" {print $10; exit}')"
GNUPGHOME="$gpg_home" gpg --batch --armor --export "$fingerprint" >"$task_dir/test-key.asc"

GNUPGHOME="$gpg_home" "$repo_root/scripts/build-validator-enroll-release.sh" \
  --output-dir "$task_dir/release-a" \
  --source-revision 0123456789abcdef0123456789abcdef01234567 \
  --source-epoch 1788570000 \
  --signing-key "$fingerprint" \
  --public-key "$task_dir/test-key.asc"
GNUPGHOME="$gpg_home" "$repo_root/scripts/build-validator-enroll-release.sh" \
  --output-dir "$task_dir/release-b" \
  --source-revision 0123456789abcdef0123456789abcdef01234567 \
  --source-epoch 1788570000 \
  --signing-key "$fingerprint" \
  --public-key "$task_dir/test-key.asc"

cmp "$task_dir/release-a/roko-validator-enroll-1.1.0.tar.gz" \
  "$task_dir/release-b/roko-validator-enroll-1.1.0.tar.gz"
cmp "$task_dir/release-a/roko-validator-enroll-1.1.0.metadata.json" \
  "$task_dir/release-b/roko-validator-enroll-1.1.0.metadata.json"
grep -F 'install-roko-validator-enroll.sh' "$task_dir/release-a/SHA256SUMS" >/dev/null
(
  cd "$task_dir/release-a"
  sha256sum --check --strict install-roko-validator-enroll.sh.sha256
)

# Replace the production fingerprint only in an isolated, re-signed fixture.
cp -a "$task_dir/release-a" "$task_dir/install-release"
sed "s/62297562B1C7053088F405DB0117DAAA677A5BF2/${fingerprint^^}/" \
  "$task_dir/install-release/install-roko-validator-enroll.sh" >"$task_dir/install-release/installer.new"
mv "$task_dir/install-release/installer.new" "$task_dir/install-release/install-roko-validator-enroll.sh"
chmod 0755 "$task_dir/install-release/install-roko-validator-enroll.sh"
(
  cd "$task_dir/install-release"
  sha256sum roko-validator-enroll-1.1.0.tar.gz \
    roko-validator-enroll-1.1.0.metadata.json \
    install-roko-validator-enroll.sh roko-release-signing-key.asc >SHA256SUMS
)
GNUPGHOME="$gpg_home" gpg --batch --yes --local-user "$fingerprint" --armor \
  --detach-sign --output "$task_dir/install-release/SHA256SUMS.asc" \
  "$task_dir/install-release/SHA256SUMS"
install_root="$task_dir/install-root"
bin_dir="$task_dir/bin"
ROKO_VALIDATOR_ENROLL_ROOT="$install_root" \
  ROKO_VALIDATOR_ENROLL_BIN_DIR="$bin_dir" \
  "$task_dir/install-release/install-roko-validator-enroll.sh" \
  --bundle-dir "$task_dir/install-release"

[[ "$("$bin_dir/roko-validator-enroll" --version)" == 'roko-validator-enroll 1.1.0' ]]
"$bin_dir/roko-validator-enroll" --help | grep -F 'Generate a public-only ROKO validator enrollment package' >/dev/null
python3 - "$install_root/1.1.0/compatibility/validator-enroll-compatibility.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["network"]["chainId"] == "52370"
assert value["runtime"] == {"maximumSpecVersion": 287, "minimumSpecVersion": 285}
assert value["tool"]["sourceRevision"] == "0123456789abcdef0123456789abcdef01234567"
PY

tampered_archive="$task_dir/tampered-archive"
cp -a "$task_dir/install-release" "$tampered_archive"
printf 'tamper' >>"$tampered_archive/roko-validator-enroll-1.1.0.tar.gz"
if ROKO_VALIDATOR_ENROLL_ROOT="$task_dir/tampered-archive-root" \
  ROKO_VALIDATOR_ENROLL_BIN_DIR="$task_dir/tampered-archive-bin" \
  "$tampered_archive/install-roko-validator-enroll.sh" --bundle-dir "$tampered_archive" \
  >"$task_dir/tampered-archive.log" 2>&1; then
  printf 'Installer accepted a release with altered archive bytes\n' >&2
  exit 1
fi
grep -Eq 'FAILED|did NOT verify|does NOT verify' "$task_dir/tampered-archive.log"

tampered_metadata="$task_dir/tampered-metadata"
cp -a "$task_dir/install-release" "$tampered_metadata"
printf ' ' >>"$tampered_metadata/roko-validator-enroll-1.1.0.metadata.json"
if ROKO_VALIDATOR_ENROLL_ROOT="$task_dir/tampered-metadata-root" \
  ROKO_VALIDATOR_ENROLL_BIN_DIR="$task_dir/tampered-metadata-bin" \
  "$tampered_metadata/install-roko-validator-enroll.sh" --bundle-dir "$tampered_metadata" \
  >"$task_dir/tampered-metadata.log" 2>&1; then
  printf 'Installer accepted release metadata with an invalid signature\n' >&2
  exit 1
fi
grep -Eq 'BAD signature|did NOT verify|does NOT verify' "$task_dir/tampered-metadata.log"

offline="$task_dir/release-a/roko-validator-enroll-offline-1.1.0.tar.gz"
(cd "$task_dir/release-a" && sha256sum --check --strict "$(basename "$offline").sha256")
printf 'validator enrollment release test ok\n'
