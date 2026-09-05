#!/usr/bin/env bash
set -euo pipefail

release_base="${ROKO_VALIDATOR_ENROLL_RELEASE_BASE:-https://downloads.roko.network/validator-tools/current}"
bundle_dir=""
install_root="${ROKO_VALIDATOR_ENROLL_ROOT:-/usr/local/lib/roko-validator-enroll}"
bin_dir="${ROKO_VALIDATOR_ENROLL_BIN_DIR:-/usr/local/bin}"
expected_fingerprint="62297562B1C7053088F405DB0117DAAA677A5BF2"

usage() {
  cat <<'EOF'
Usage: install-roko-validator-enroll.sh [OPTIONS]

Downloads and verifies the signed current release, or installs from an
extracted offline bundle. No development checkout is required.

Options:
  --release-base URL     Signed release directory
  --bundle-dir PATH      Extracted offline release directory
  --install-root PATH    Versioned installation root
  --bin-dir PATH         Command-link directory
  -h, --help             Show this help
EOF
}

while (($#)); do
  case "$1" in
    --release-base) release_base="${2:-}"; shift ;;
    --bundle-dir) bundle_dir="${2:-}"; shift ;;
    --install-root) install_root="${2:-}"; shift ;;
    --bin-dir) bin_dir="${2:-}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for command_name in curl gpg python3 sha256sum tar; do
  if [[ "$command_name" == curl && -n "$bundle_dir" ]]; then continue; fi
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done
[[ "$install_root" == /* && "$install_root" != / ]] || { printf 'Install root must be an absolute non-root path\n' >&2; exit 2; }
[[ "$bin_dir" == /* && "$bin_dir" != / ]] || { printf 'Bin directory must be an absolute non-root path\n' >&2; exit 2; }

task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT
if [[ -n "$bundle_dir" ]]; then
  [[ -d "$bundle_dir" ]] || { printf 'Offline bundle directory not found: %s\n' "$bundle_dir" >&2; exit 1; }
  cp "$bundle_dir"/* "$task_dir/"
else
  for file in SHA256SUMS SHA256SUMS.asc roko-release-signing-key.asc; do
    curl --fail --location --silent --show-error "$release_base/$file" --output "$task_dir/$file"
  done
fi

key_inspect_home="$task_dir/key-inspect"
install -d -m 0700 "$key_inspect_home"
actual_fingerprint="$(GNUPGHOME="$key_inspect_home" gpg --batch --with-colons --import-options show-only --import "$task_dir/roko-release-signing-key.asc" 2>/dev/null | awk -F: '$1 == "fpr" {print toupper($10); exit}')"
[[ "$actual_fingerprint" == "$expected_fingerprint" ]] || {
  printf 'Release key fingerprint mismatch: expected %s\n' "$expected_fingerprint" >&2
  exit 1
}
gpg_home="$task_dir/gnupg"
install -d -m 0700 "$gpg_home"
GNUPGHOME="$gpg_home" gpg --batch --quiet --import "$task_dir/roko-release-signing-key.asc"
GNUPGHOME="$gpg_home" gpg --batch --verify "$task_dir/SHA256SUMS.asc" "$task_dir/SHA256SUMS"
installer_expected="$(awk '$2 == "install-roko-validator-enroll.sh" || $2 == "*install-roko-validator-enroll.sh" {print $1; exit}' "$task_dir/SHA256SUMS")"
installer_actual="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
[[ -n "$installer_expected" && "$installer_actual" == "$installer_expected" ]] || {
  printf 'The running installer does not match the signed release manifest\n' >&2
  exit 1
}

metadata_name="$(awk '{print $2}' "$task_dir/SHA256SUMS" | sed 's#^\*##' | grep -E '^roko-validator-enroll-[0-9]+\.[0-9]+\.[0-9]+\.metadata\.json$' | head -1)"
[[ -n "$metadata_name" ]] || { printf 'Signed checksums do not name release metadata\n' >&2; exit 1; }
if [[ -z "$bundle_dir" ]]; then
  curl --fail --location --silent --show-error "$release_base/$metadata_name" --output "$task_dir/$metadata_name"
  curl --fail --location --silent --show-error "$release_base/$metadata_name.asc" --output "$task_dir/$metadata_name.asc"
fi
GNUPGHOME="$gpg_home" gpg --batch --verify "$task_dir/$metadata_name.asc" "$task_dir/$metadata_name"

readarray -t release_fields < <(python3 - "$task_dir/$metadata_name" <<'PY'
import json
import re
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("schema") != "roko.validator-enroll-release.v1": raise SystemExit("Unsupported release metadata schema")
version = value.get("tool", {}).get("version", "")
revision = value.get("source", {}).get("revision", "")
artifact = value.get("artifact", {})
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version): raise SystemExit("Invalid release version")
if not re.fullmatch(r"[0-9a-f]{40}", revision): raise SystemExit("Invalid source revision")
if not re.fullmatch(r"roko-validator-enroll-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz", artifact.get("file", "")): raise SystemExit("Invalid archive name")
if not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", "")): raise SystemExit("Invalid archive digest")
print(version)
print(revision)
print(artifact["file"])
print(artifact["sha256"])
print(value["compatibility"]["sha256"])
PY
)
version="${release_fields[0]}"
revision="${release_fields[1]}"
archive_name="${release_fields[2]}"
archive_sha="${release_fields[3]}"
compatibility_sha="${release_fields[4]}"
if [[ -z "$bundle_dir" ]]; then
  curl --fail --location --silent --show-error "$release_base/$archive_name" --output "$task_dir/$archive_name"
fi
printf '%s  %s\n' "$archive_sha" "$task_dir/$archive_name" | sha256sum --check --strict

extract_dir="$task_dir/extract"
mkdir "$extract_dir"
tar -xzf "$task_dir/$archive_name" -C "$extract_dir" --no-same-owner
package_root="$extract_dir/roko-validator-enroll-$version"
[[ -x "$package_root/bin/roko-validator-enroll" && -x "$package_root/bin/roko-session-key-window" ]] || {
  printf 'Release archive does not contain both enrollment commands\n' >&2
  exit 1
}
printf '%s  %s\n' "$compatibility_sha" "$package_root/compatibility/validator-enroll-compatibility.json" | sha256sum --check --strict
python3 - "$package_root/compatibility/validator-enroll-compatibility.json" "$version" "$revision" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("schema") != "roko.validator-enroll-compatibility.v1": raise SystemExit("Unsupported compatibility schema")
if value.get("tool", {}).get("version") != sys.argv[2]: raise SystemExit("Compatibility version mismatch")
if value.get("tool", {}).get("sourceRevision") != sys.argv[3]: raise SystemExit("Compatibility revision mismatch")
network = value.get("network", {})
runtime = value.get("runtime", {})
if network.get("chainId") != "52370" or network.get("genesisHash") != "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb":
    raise SystemExit("Compatibility network mismatch")
if runtime.get("minimumSpecVersion") > runtime.get("maximumSpecVersion"): raise SystemExit("Invalid runtime compatibility range")
PY

destination="$install_root/$version"
install -d -m 0755 "$install_root" "$bin_dir"
rm -rf -- "$destination.new"
install -d -m 0755 "$destination.new"
cp -a "$package_root/." "$destination.new/"
rm -rf -- "$destination"
mv "$destination.new" "$destination"
ln -sfn "$destination/bin/roko-validator-enroll" "$bin_dir/roko-validator-enroll"
ln -sfn "$destination/bin/roko-session-key-window" "$bin_dir/roko-session-key-window"

version_output="$("$bin_dir/roko-validator-enroll" --version)"
[[ "$version_output" == "roko-validator-enroll $version" ]] || {
  printf 'Installed command returned unexpected version: %s\n' "$version_output" >&2
  exit 1
}
"$bin_dir/roko-validator-enroll" --help | grep -F 'Generate a public-only ROKO validator enrollment package' >/dev/null
printf 'Installed: %s\n' "$(readlink -f "$bin_dir/roko-validator-enroll")"
printf 'Version: %s\n' "$version_output"
printf 'Compatibility: %s\n' "$destination/compatibility/validator-enroll-compatibility.json"
