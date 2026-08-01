#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${CLOCK_PROVIDER:-chrony}" == timebeat ]]; then
  as_root systemctl restart timebeat.service
  systemctl is-active --quiet timebeat.service
else
  if systemctl cat chronyd.service >/dev/null 2>&1; then
    clock_unit=chronyd.service
  else
    clock_unit=chrony.service
  fi
  as_root systemctl restart "$clock_unit"
  chronyc waitsync 60 0.01
fi
as_root systemctl restart roko-node.service
systemctl is-active --quiet roko-node.service
log "Clock and ROKO services restarted; rerun the full verification step."
