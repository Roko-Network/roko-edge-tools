#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="$root/installer/scripts/install-roko-service.sh"
guided="$root/bin/roko-guided-install"
apps02=12D3KooWDwrPobC2ZpmjYJwgTFpCd7uyaeqXu1FQctmsdKffsmwN
titan=12D3KooWFXjLThfEcwWj6T5E8ir1PAVGSgMgmpPjXBSQuXWvAz5y
addresses="/ip4/66.94.104.190/tcp/30334/p2p/$apps02
/ip4/66.94.104.190/tcp/30335/p2p/$titan"
flag='--timesync-participation-profile'

fail() { echo "$1" >&2; exit 1; }

render() {
  env -u ROKO_TIMING_PROFILE ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="$addresses" \
    "$service" --node-name fixture-validator --render-unit "$@"
}

for runtime in native docker; do
  for clock in chrony timebeat; do
    unit="$(render --runtime "$runtime" --clock-provider "$clock" --validator-candidate)"
    grep -Fx -- "  $flag early-testnet \\" <<<"$unit" >/dev/null ||
      fail "$runtime/$clock validator-candidate unit does not default to early-testnet"
    [[ "$(grep -cF -- "$flag" <<<"$unit")" -eq 1 ]] ||
      fail "$runtime/$clock validator-candidate unit renders the profile more than once"

    unit="$(render --runtime "$runtime" --clock-provider "$clock" --validator-candidate --timing-profile strict)"
    grep -Fx -- "  $flag strict \\" <<<"$unit" >/dev/null ||
      fail "$runtime/$clock --timing-profile strict did not render strict"
    ! grep -F -- 'early-testnet' <<<"$unit" >/dev/null ||
      fail "$runtime/$clock strict unit still mentions early-testnet"

    unit="$(ROKO_TIMING_PROFILE=strict ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="$addresses" \
      "$service" --runtime "$runtime" --clock-provider "$clock" --node-name fixture-validator \
      --validator-candidate --render-unit)"
    grep -Fx -- "  $flag strict \\" <<<"$unit" >/dev/null ||
      fail "$runtime/$clock ROKO_TIMING_PROFILE=strict was not honoured"

    for role_args in "" "--archive" "--observer"; do
      # shellcheck disable=SC2086
      unit="$(render --runtime "$runtime" --clock-provider "$clock" $role_args)"
      ! grep -F -- "$flag" <<<"$unit" >/dev/null ||
        fail "$runtime/$clock non-validator role '${role_args:-full}' rendered $flag"
    done
  done
done

# The flag sits with the other timesync flags and the unit stays non-authoring.
unit="$(render --runtime native --clock-provider chrony --validator-candidate)"
grep -A1 -F -- '--timesync-chrony-socket /run/chrony/chronyd.sock' <<<"$unit" |
  grep -F -- "$flag early-testnet" >/dev/null || fail "profile flag is not next to the timesync lines"
! grep -E -- '(^|[[:space:]])--validator([[:space:]]|$)' <<<"$unit" >/dev/null ||
  fail "validator-candidate unit unexpectedly enables authoring"

# Invalid values and misuse fail clearly.
for bad in "" STRICT early relaxed "early-testnet;x"; do
  if err="$(render --runtime native --clock-provider chrony --validator-candidate \
    --timing-profile "$bad" 2>&1)"; then
    fail "accepted invalid --timing-profile '$bad'"
  fi
  grep -F "must be early-testnet or strict" <<<"$err" >/dev/null ||
    fail "invalid --timing-profile '$bad' failed without a clear message"
done
if ROKO_TIMING_PROFILE=bogus ROKO_CHRONY_GID=104 ROKO_AUTHORITY_ADDRESSES="$addresses" \
  "$service" --runtime native --clock-provider chrony --node-name fixture-validator \
  --validator-candidate --render-unit >/dev/null 2>&1; then
  fail "accepted invalid ROKO_TIMING_PROFILE"
fi
if render --runtime native --clock-provider chrony --timing-profile strict >/dev/null 2>&1; then
  fail "accepted --timing-profile for a non-validator role"
fi

# Guided installer threads and reports the profile.
guided_run() {
  env -u ROKO_TIMING_PROFILE NODE_NAME=fixture NODE_ROLE="$1" RUNTIME=native \
    SYNC_TIMEOUT_SECONDS=60 REPORT_PATH=/tmp/roko-timing-profile-readiness.txt TIME_REGION=global \
    "$guided" --time-stack chrony --non-interactive --dry-run "${@:2}"
}
grep -F "Timing profile: early-testnet" <<<"$(guided_run validator-candidate)" >/dev/null ||
  fail "guided validator-candidate plan does not default to early-testnet"
grep -F "Timing profile: strict" <<<"$(guided_run validator-candidate --timing-profile strict)" >/dev/null ||
  fail "guided --timing-profile strict was not threaded"
grep -F "Timing profile: not applicable" <<<"$(guided_run full)" >/dev/null ||
  fail "guided full-role plan should not select a timing profile"
if guided_run validator-candidate --timing-profile relaxed >/dev/null 2>&1; then
  fail "guided installer accepted an invalid timing profile"
fi
if guided_run full --timing-profile strict >/dev/null 2>&1; then
  fail "guided installer accepted --timing-profile for the full role"
fi
# shellcheck disable=SC2016
grep -F -- '--timing-profile "${ROKO_TIMING_PROFILE:-early-testnet}"' \
  "$root/installer/scripts/install-roko-node.sh" >/dev/null ||
  fail "install-roko-node.sh does not thread the timing profile"

echo "timing profile contract ok"
