#!/usr/bin/env bash
set -euo pipefail

ROKO_RPC_URL="${ROKO_RPC_URL:-http://127.0.0.1:9944}"
ROKO_SERVICE="${ROKO_SERVICE:-roko-node}"
ROKO_BASE_PATH="${ROKO_BASE_PATH:-/var/lib/roko}"
ROKO_NTP_SOURCE="${ROKO_NTP_SOURCE:-ntp01.roko.network}"

section() {
  printf '\n== %s ==\n' "$*"
}

ok() {
  printf 'ok: %s\n' "$*"
}

warn() {
  printf 'warn: %s\n' "$*" >&2
}

have() {
  command -v "$1" >/dev/null 2>&1
}

run_optional() {
  local label="$1"
  shift
  if "$@"; then
    return 0
  fi
  warn "$label failed"
  return 0
}

json_rpc() {
  local method="$1"
  local params="${2:-[]}"
  if have curl; then
    curl --fail --silent --show-error --max-time "${ROKO_RPC_TIMEOUT:-8}" \
      -H 'content-type: application/json' \
      --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"${method}\",\"params\":${params}}" \
      "$ROKO_RPC_URL"
  else
    return 127
  fi
}
