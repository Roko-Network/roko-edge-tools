#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[[ "${NODE_ROLE:-}" == observer ]] || {
  log "ROKO observer key step skipped for role ${NODE_ROLE:-unknown}."
  exit 0
}

[[ -t 0 ]] || fail "Observer key insertion requires an interactive terminal."
as_root systemctl stop roko-node.service || true

if [[ "${RUNTIME:-native}" == native ]]; then
  require_command runuser
  as_root runuser -u roko -- /usr/local/bin/roko-node key insert \
    --base-path /var/lib/roko \
    --chain /etc/roko/roko-testnet-v2.json \
    --key-type ptp2 \
    --scheme sr25519
else
  # shellcheck disable=SC1091
  source /etc/roko/node-image.env
  as_root docker run --rm -it \
    --mount type=bind,src=/var/lib/roko,dst=/data \
    --mount type=bind,src=/etc/roko/roko-testnet-v2.json,dst=/etc/roko/roko-testnet-v2.json,readonly \
    "$ROKO_IMAGE" key insert \
    --base-path /data \
    --chain /etc/roko/roko-testnet-v2.json \
    --key-type ptp2 \
    --scheme sr25519
fi

log "Inserted the dedicated ROKO libp2p PTP² observer key without placing its secret in argv."
