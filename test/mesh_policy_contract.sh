#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="$root/installer/scripts/install-roko-service.sh"
apps02=12D3KooWDwrPobC2ZpmjYJwgTFpCd7uyaeqXu1FQctmsdKffsmwN
titan=12D3KooWFXjLThfEcwWj6T5E8ir1PAVGSgMgmpPjXBSQuXWvAz5y
addresses="/ip4/66.94.104.190/tcp/30334/p2p/$apps02
/ip4/66.94.104.190/tcp/30335/p2p/$titan"
bootnode=/dns4/boot.roko.network/tcp/30333/p2p/12D3KooWKSBZRtSiGKo8ueJtazCHT89LaBi6ZAtzgbeznf4NtVGj

fail() { echo "$1" >&2; exit 1; }

render() {
  env -u ROKO_TIMING_PROFILE ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="$addresses" \
    "$service" --node-name fixture-mesh --render-unit "$@"
}

for runtime in native docker; do
  for clock in chrony timebeat; do
    for role in "" --archive --observer --validator-candidate; do
      label="$runtime/$clock/${role:-full}"
      unit="$(render --runtime "$runtime" --clock-provider "$clock" $role)"
      for line in "--timesync-convergence-threshold-ns 5000000" "--timesync-lucky-threshold-ns 10000000"; do
        grep -Fx -- "  $line \\" <<<"$unit" >/dev/null || fail "$label unit is missing '$line'"
        [[ "$(grep -cF -- "${line% *}" <<<"$unit")" -eq 1 ]] || fail "$label unit renders '${line% *}' more than once"
      done
      grep -F -- "--bootnodes $bootnode" <<<"$unit" >/dev/null || fail "$label unit does not use the plain-TCP bootnode"
      if grep -E -- '/ws(/|$| )' <<<"$unit" >/dev/null; then
        fail "$label unit renders a /ws multiaddress"
      fi
    done
  done
done

echo "mesh policy contract passed"
