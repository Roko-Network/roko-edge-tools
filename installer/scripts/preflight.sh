#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

validate_common_params
load_os_release
require_command bash
require_command curl
require_command python3
require_command sha256sum
require_command systemctl

case "$(uname -m)" in
  x86_64|aarch64|arm64) ;;
  *) fail "Unsupported architecture: $(uname -m)" ;;
esac

case "$ROKO_DISTRO $ROKO_DISTRO_LIKE" in
  *debian*|*ubuntu*|*fedora*|*rhel*|*centos*) ;;
  *) fail "Supported distributions are Debian/Ubuntu and Fedora/RHEL-family Linux." ;;
esac

minimum_gb=200
[[ "$NODE_ROLE" == archive ]] && minimum_gb=1000
available_gb="$(df -Pk /var/lib 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')"
[[ "$available_gb" =~ ^[0-9]+$ ]] || fail "Could not determine free space under /var/lib."
(( available_gb >= minimum_gb )) ||
  fail "$NODE_ROLE setup requires at least ${minimum_gb} GiB free under /var/lib; found ${available_gb} GiB."

if [[ "$RUNTIME" == docker ]]; then
  require_command docker
  docker info >/dev/null 2>&1 || fail "Docker is installed but its daemon is unavailable to this user."
fi

log "Preflight passed: distro=$ROKO_DISTRO arch=$(uname -m) role=$NODE_ROLE runtime=$RUNTIME free=${available_gb}GiB"
