#!/usr/bin/env bash
set -euo pipefail

release_base="${ROKO_RELEASE_BASE:-https://downloads.roko.network/releases/current}"
env_file="${ROKO_IMAGE_ENV_FILE:-/etc/roko/node-image.env}"
dry_run=false

usage() {
  cat <<'EOF'
Usage: install-roko-docker.sh [--dry-run]

Downloads the current architecture-specific offline ROKO testnet image,
verifies it against the release checksum manifest, validates the image's
source revision and validator time-source tools, and records its immutable
local image ID in /etc/roko/node-image.env.

Environment overrides:
  ROKO_RELEASE_BASE   Artifact base URL
  ROKO_IMAGE_ENV_FILE Destination environment file
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) dry_run=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$(uname -m)" in
  x86_64) roko_arch=amd64 ;;
  aarch64|arm64) roko_arch=arm64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

archive="roko-node-testnet-docker-${roko_arch}.tar.gz"
echo "ROKO Docker installation"
echo "  architecture: ${roko_arch}"
echo "  release: ${release_base}"
echo "  archive: ${archive}"
echo "  digest file: ${env_file}"

if "$dry_run"; then
  exit 0
fi

for command_name in curl docker jq sha256sum; do
  command -v "$command_name" >/dev/null || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done
docker info >/dev/null

task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT
for filename in SHA256SUMS BUILD-METADATA.json "$archive"; do
  curl --fail --location --silent --show-error \
    "$release_base/$filename" --output "$task_dir/$filename"
done
(
  cd "$task_dir"
  sha256sum --check --ignore-missing SHA256SUMS
)

expected_revision="$(jq -er '.source_revision | select(test("^[0-9a-f]{40}$"))' "$task_dir/BUILD-METADATA.json")"
declared_archive="$(jq -er --arg arch "$roko_arch" '.offline_images[$arch]' "$task_dir/BUILD-METADATA.json")"
[[ "$declared_archive" == "$archive" ]] || {
  echo "Release metadata names an unexpected ${roko_arch} image archive: $declared_archive" >&2
  exit 1
}

load_output="$(docker load --input "$task_dir/$archive")"
printf '%s\n' "$load_output"
image_ref="$(
  printf '%s\n' "$load_output" |
    sed -n -e 's/^Loaded image: //p' -e 's/^Loaded image ID: //p' |
    tail -n 1
)"
[[ -n "$image_ref" ]] || {
  echo "Docker did not report the loaded ROKO image reference." >&2
  exit 1
}

image_id="$(docker image inspect "$image_ref" --format '{{.Id}}')"
image_arch="$(docker image inspect "$image_ref" --format '{{.Architecture}}')"
image_revision="$(docker image inspect "$image_ref" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
[[ "$image_arch" == "$roko_arch" ]] || {
  echo "Loaded image architecture $image_arch does not match host architecture $roko_arch." >&2
  exit 1
}
[[ "$image_revision" == "$expected_revision" ]] || {
  echo "Loaded image revision does not match BUILD-METADATA.json." >&2
  exit 1
}

docker run --rm --entrypoint /bin/sh "$image_id" -ec '
  test -x /usr/bin/chronyc
  test -x /usr/sbin/ethtool
  ! command -v chronyd >/dev/null 2>&1
'
docker run --rm "$image_id" --version

task_env="$task_dir/node-image.env"
printf 'ROKO_IMAGE=%s\n' "$image_id" >"$task_env"
env_dir="$(dirname "$env_file")"
if [[ "$(id -u)" -eq 0 ]]; then
  install -d -o root -g root -m 0755 "$env_dir"
  install -o root -g root -m 0644 "$task_env" "$env_file"
elif command -v sudo >/dev/null; then
  sudo install -d -o root -g root -m 0755 "$env_dir"
  sudo install -o root -g root -m 0644 "$task_env" "$env_file"
else
  echo "Root access is required to install $env_file (sudo not found)." >&2
  exit 1
fi

echo "Recorded checksum-verified image $image_id from source revision $expected_revision in $env_file"
