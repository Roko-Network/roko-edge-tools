#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[roko-setup] %s\n' "$*"
}

fail() {
  printf '[roko-setup] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    fail "Root privileges are required for: $*"
  fi
}

load_os_release() {
  [[ -r /etc/os-release ]] || fail "This installer requires a Linux distribution with /etc/os-release."
  # shellcheck disable=SC1091
  source /etc/os-release
  # These globals are consumed by scripts that source this library.
  # shellcheck disable=SC2034
  ROKO_DISTRO="${ID,,}"
  # shellcheck disable=SC2034
  ROKO_DISTRO_LIKE="${ID_LIKE:-}"
}

validate_common_params() {
  : "${NODE_NAME:?NODE_NAME is required}"
  : "${NODE_ROLE:?NODE_ROLE is required}"
  : "${RUNTIME:?RUNTIME is required}"
  [[ "$NODE_NAME" =~ ^[A-Za-z0-9._-]{1,64}$ ]] ||
    fail "NODE_NAME must use 1-64 letters, digits, dots, underscores, or hyphens."
  [[ "$NODE_ROLE" == full || "$NODE_ROLE" == archive || "$NODE_ROLE" == observer || "$NODE_ROLE" == validator-candidate ]] ||
    fail "NODE_ROLE must be full, archive, observer, or validator-candidate."
  [[ "$RUNTIME" == native || "$RUNTIME" == docker ]] ||
    fail "RUNTIME must be native or docker."
}
