#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

report_path="${REPORT_PATH:-./roko-install-readiness.txt}"
umask 077
{
  printf 'ROKO installation readiness\n'
  printf 'generated_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'node_name=%s\n' "${NODE_NAME:?}"
  printf 'node_role=%s\n' "${NODE_ROLE:?}"
  printf 'runtime=%s\n' "${RUNTIME:?}"
  printf 'clock_provider=%s\n' "${CLOCK_PROVIDER:-chrony}"
  printf 'service_active=%s\n' "$(systemctl is-active roko-node.service)"
  printf 'binary='
  if [[ "$RUNTIME" == native ]]; then
    /usr/local/bin/roko-node --version
  else
    sed -n 's/^ROKO_IMAGE=//p' /etc/roko/node-image.env
  fi
  printf 'next_step=%s\n' "$(
    if [[ "$NODE_ROLE" == validator-candidate ]]; then
      printf 'operator-reviewed validator key provisioning and enrollment'
    else
      printf 'routine monitoring'
    fi
  )"
} >"$report_path"
log "Wrote value-free readiness report: $report_path"
