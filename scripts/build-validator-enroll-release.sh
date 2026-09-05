#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$repo_root/dist"
source_revision=""
source_epoch=""
signing_key=""
public_key="$repo_root/release/roko-release-signing-key.asc"
unsigned_test_only=false

usage() {
  cat <<'EOF'
Usage: build-validator-enroll-release.sh [OPTIONS]

Builds deterministic online and offline validator-enrollment release bundles.
Production builds require a detached OpenPGP signature.

Options:
  --output-dir PATH       Output directory (default: ./dist)
  --source-revision SHA   Exact 40-character source revision (default: HEAD)
  --source-epoch EPOCH    Reproducible update timestamp (default: commit time)
  --signing-key FPR       OpenPGP signing fingerprint
  --public-key PATH       Armored public key bundled for offline verification
  --unsigned-test-only    Build without signatures; never publish this output
  -h, --help              Show this help
EOF
}

while (($#)); do
  case "$1" in
    --output-dir) output_dir="${2:-}"; shift ;;
    --source-revision) source_revision="${2:-}"; shift ;;
    --source-epoch) source_epoch="${2:-}"; shift ;;
    --signing-key) signing_key="${2:-}"; shift ;;
    --public-key) public_key="${2:-}"; shift ;;
    --unsigned-test-only) unsigned_test_only=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for command_name in git python3 sha256sum stat tar gzip; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done

version="$(tr -d '[:space:]' <"$repo_root/VERSION")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  printf 'VERSION must contain one semantic version\n' >&2
  exit 1
}
source_revision="${source_revision:-$(git -C "$repo_root" rev-parse HEAD)}"
[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'Source revision must be a full lowercase Git commit hash\n' >&2
  exit 1
}
source_epoch="${source_epoch:-$(git -C "$repo_root" show -s --format=%ct "$source_revision")}" 
[[ "$source_epoch" =~ ^[0-9]{9,}$ ]] || {
  printf 'Source epoch must be a Unix timestamp\n' >&2
  exit 1
}
if ! "$unsigned_test_only"; then
  command -v gpg >/dev/null 2>&1 || { printf 'gpg is required for a publishable build\n' >&2; exit 1; }
  [[ "$signing_key" =~ ^[0-9A-Fa-f]{40}$ ]] || {
    printf 'A full --signing-key fingerprint is required for a publishable build\n' >&2
    exit 1
  }
fi
[[ -r "$public_key" ]] || { printf 'Public signing key is unreadable: %s\n' "$public_key" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
package_name="roko-validator-enroll-$version"
package_root="$stage/$package_name"
mkdir -p "$package_root/bin" "$package_root/lib" "$package_root/contracts" \
  "$package_root/compatibility" "$package_root/scripts" "$output_dir"

install -m 0755 "$repo_root/bin/roko-validator-enroll" "$package_root/bin/"
install -m 0755 "$repo_root/bin/roko-session-key-window" "$package_root/bin/"
install -m 0644 "$repo_root/lib/validator_enrollment.py" "$package_root/lib/"
install -m 0644 "$repo_root/contracts/validator-enrollment-v1.schema.json" "$package_root/contracts/"
install -m 0755 "$repo_root/scripts/install-roko-validator-enroll.sh" "$package_root/scripts/"
install -m 0644 "$repo_root/VERSION" "$package_root/"
install -m 0644 "$public_key" "$package_root/roko-release-signing-key.asc"

python3 - "$repo_root/release/validator-enroll-compatibility.template.json" \
  "$package_root/compatibility/validator-enroll-compatibility.json" \
  "$version" "$source_revision" <<'PY'
import json
import pathlib
import sys

source, target, version, revision = sys.argv[1:]
text = pathlib.Path(source).read_text(encoding="utf-8")
value = json.loads(text.replace("@VERSION@", version).replace("@SOURCE_REVISION@", revision))
pathlib.Path(target).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

archive="$output_dir/$package_name.tar.gz"
tar --sort=name --mtime="@$source_epoch" --owner=0 --group=0 --numeric-owner \
  --pax-option=delete=atime,delete=ctime -C "$stage" -cf - "$package_name" | gzip -n >"$archive"
archive_sha="$(sha256sum "$archive" | awk '{print $1}')"
archive_bytes="$(stat -c %s "$archive")"
compatibility_sha="$(sha256sum "$package_root/compatibility/validator-enroll-compatibility.json" | awk '{print $1}')"
updated_at="$(python3 - "$source_epoch" <<'PY'
import datetime
import sys
print(datetime.datetime.fromtimestamp(int(sys.argv[1]), datetime.timezone.utc).isoformat().replace("+00:00", "Z"))
PY
)"
metadata="$output_dir/$package_name.metadata.json"
python3 - "$metadata" "$version" "$source_revision" "$updated_at" \
  "$(basename "$archive")" "$archive_sha" "$archive_bytes" "$compatibility_sha" <<'PY'
import json
import pathlib
import sys

target, version, revision, updated, archive, digest, size, compatibility_digest = sys.argv[1:]
value = {
    "schema": "roko.validator-enroll-release.v1",
    "tool": {"name": "roko-validator-enroll", "version": version},
    "source": {
        "repository": "https://github.com/Roko-Network/roko-edge-tools",
        "revision": revision,
    },
    "artifact": {
        "file": archive,
        "sha256": digest,
        "bytes": int(size),
        "mediaType": "application/gzip",
    },
    "compatibility": {
        "file": "compatibility/validator-enroll-compatibility.json",
        "sha256": compatibility_digest,
    },
    "updatedAt": updated,
}
pathlib.Path(target).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

cp "$public_key" "$output_dir/roko-release-signing-key.asc"
install -m 0755 "$repo_root/scripts/install-roko-validator-enroll.sh" \
  "$output_dir/install-roko-validator-enroll.sh"
(
  cd "$output_dir"
  sha256sum install-roko-validator-enroll.sh >install-roko-validator-enroll.sh.sha256
)
checksums="$output_dir/SHA256SUMS"
(
  cd "$output_dir"
  sha256sum "$(basename "$archive")" "$(basename "$metadata")" \
    install-roko-validator-enroll.sh roko-release-signing-key.asc >"$(basename "$checksums")"
)

if ! "$unsigned_test_only"; then
  gpg --batch --yes --local-user "$signing_key" --armor --detach-sign --output "$metadata.asc" "$metadata"
  gpg --batch --yes --local-user "$signing_key" --armor --detach-sign --output "$checksums.asc" "$checksums"
fi

offline_stage="$stage/offline"
mkdir -p "$offline_stage"
cp "$archive" "$metadata" "$checksums" "$output_dir/roko-release-signing-key.asc" \
  "$output_dir/install-roko-validator-enroll.sh" "$offline_stage/"
if ! "$unsigned_test_only"; then
  cp "$metadata.asc" "$checksums.asc" "$offline_stage/"
fi
offline="$output_dir/roko-validator-enroll-offline-$version.tar.gz"
tar --sort=name --mtime="@$source_epoch" --owner=0 --group=0 --numeric-owner \
  --pax-option=delete=atime,delete=ctime -C "$offline_stage" -cf - . | gzip -n >"$offline"
sha256sum "$offline" >"$offline.sha256"

printf 'Release archive: %s\n' "$archive"
printf 'Release metadata: %s\n' "$metadata"
printf 'Offline bundle: %s\n' "$offline"
if "$unsigned_test_only"; then
  printf 'UNPUBLISHABLE: signatures intentionally omitted for test-only output\n'
else
  printf 'Detached signatures: %s %s\n' "$metadata.asc" "$checksums.asc"
fi
