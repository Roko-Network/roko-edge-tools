#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
apps02=12D3KooWDwrPobC2ZpmjYJwgTFpCd7uyaeqXu1FQctmsdKffsmwN
titan=12D3KooWFXjLThfEcwWj6T5E8ir1PAVGSgMgmpPjXBSQuXWvAz5y
addresses="/ip4/66.94.104.190/tcp/30334/p2p/$apps02
/ip4/66.94.104.190/tcp/30335/p2p/$titan"

unit="$(ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="$addresses" \
  "$root/installer/scripts/install-roko-service.sh" --runtime docker \
  --node-name fixture-validator --clock-provider chrony --validator-candidate --render-unit)"
grep -F -- "--reserved-nodes /ip4/66.94.104.190/tcp/30334/p2p/$apps02" <<<"$unit" >/dev/null
grep -F -- "--reserved-nodes /ip4/66.94.104.190/tcp/30335/p2p/$titan" <<<"$unit" >/dev/null
if ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="/ip4/10.0.42.111/tcp/30333/p2p/$apps02" \
  "$root/installer/scripts/install-roko-service.sh" --runtime docker \
  --node-name fixture-validator --clock-provider chrony --validator-candidate --render-unit \
  >/dev/null 2>&1; then
  echo "Service renderer accepted fewer than two published authorities" >&2
  exit 1
fi

echo "authority service contract ok"
