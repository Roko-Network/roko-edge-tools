#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

timeout_seconds="${SYNC_TIMEOUT_SECONDS:-3600}"
expected_genesis="0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"
rpc_url=http://127.0.0.1:9944

as_root systemctl enable --now roko-node.service

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
  response="$(
    curl --fail --silent --show-error --max-time 10 "$rpc_url" \
      -H 'content-type: application/json' \
      --data '[
        {"jsonrpc":"2.0","id":1,"method":"chain_getBlockHash","params":[0]},
        {"jsonrpc":"2.0","id":2,"method":"system_health","params":[]},
        {"jsonrpc":"2.0","id":3,"method":"system_localPeerId","params":[]},
        {"jsonrpc":"2.0","id":4,"method":"chain_getFinalizedHead","params":[]},
        {"jsonrpc":"2.0","id":5,"method":"temporal_getMeshState","params":[]},
        {"jsonrpc":"2.0","id":6,"method":"system_nodeRoles","params":[]}
      ]' 2>/dev/null || true
  )"
  if [[ -n "$response" ]] && python3 - "$expected_genesis" "$response" <<'PY'
import json
import sys

expected, raw = sys.argv[1], sys.argv[2]
items = {item.get("id"): item for item in json.loads(raw)}
if items.get(1, {}).get("result") != expected:
    raise SystemExit(1)
health = items.get(2, {}).get("result") or {}
if health.get("isSyncing") is not False or int(health.get("peers", 0)) < 1:
    raise SystemExit(1)
if not items.get(3, {}).get("result") or not items.get(4, {}).get("result"):
    raise SystemExit(1)
mesh = items.get(5, {}).get("result") or {}
if not isinstance(mesh.get("peerCount"), int):
    raise SystemExit(1)
roles = items.get(6, {}).get("result") or []
if "Authority" in roles:
    raise SystemExit(1)
PY
  then
    first_peer="$(python3 - "$response" <<'PY'
import json, sys
print(next(item["result"] for item in json.loads(sys.argv[1]) if item.get("id") == 3))
PY
)"
    first_finalized="$(python3 - "$response" <<'PY'
import json, sys
print(next(item["result"] for item in json.loads(sys.argv[1]) if item.get("id") == 4))
PY
)"
    sleep 15
    second_response="$(
      curl --fail --silent --show-error --max-time 10 "$rpc_url" \
        -H 'content-type: application/json' \
        --data '[
          {"jsonrpc":"2.0","id":3,"method":"system_localPeerId","params":[]},
          {"jsonrpc":"2.0","id":4,"method":"chain_getFinalizedHead","params":[]}
        ]'
    )"
    readarray -t second_values < <(python3 - "$second_response" <<'PY'
import json, sys
items = {item.get("id"): item for item in json.loads(sys.argv[1])}
print(items[3]["result"])
print(items[4]["result"])
PY
)
    second_peer="${second_values[0]}"
    second_finalized="${second_values[1]}"
    [[ "$first_peer" == "$second_peer" ]] ||
      fail "The node local peer identity changed across observations."
    [[ "$first_finalized" != "$second_finalized" ]] ||
      fail "The node is synchronized but finalized head did not advance across observations."
    log "Genesis, ROKO peer connectivity, ROKO time-mesh RPC, non-authoring role, full synchronization, persistent peer identity, and advancing finality verified."
    exit 0
  fi
  log "Waiting for P2P synchronization and advancing finality..."
  sleep 15
done

fail "Node did not satisfy the synchronization gate within ${timeout_seconds} seconds."
