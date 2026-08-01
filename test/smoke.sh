#!/usr/bin/env bash
set -euo pipefail

bash -n lib/roko-edge-common.sh
bash -n bin/roko-edge-doctor
bash -n bin/roko-time-health
bash -n bin/roko-node-tail
bash -n bin/roko-edge-report
bash -n bin/roko-seed-refresh
bash -n bin/roko-guided-install
for installer_script in installer/scripts/*.sh; do
  bash -n "$installer_script"
done
python3 -m py_compile bin/roko-rpc-health

grep -R "ntp01.roko.network" README.md examples docs bin lib >/dev/null
grep -R "/roko/timesync/1" README.md docs >/dev/null
grep -R "bittorrent-seeding" README.md examples bin >/dev/null
grep -R "setup.aiwg.io/v1" installer/*.yaml >/dev/null
grep -R "www.timebeat.app/downloads/software" README.md installer >/dev/null
grep -R "does not redistribute" README.md installer >/dev/null
grep -F "wait for explicit operator approval" installer/AGENT-INSTALL.md >/dev/null
grep -F "Do not include secrets" installer/AGENT-INSTALL.md >/dev/null
grep -F "ROKO chain P2P: enabled via the public bootnode" bin/roko-guided-install >/dev/null
grep -F "temporal_getMeshState" installer/scripts/start-and-verify.sh >/dev/null
grep -F "roko_ptp2_mode=" installer/scripts/write-readiness-report.sh >/dev/null
grep -F "10.101.101.123" installer/timebeat-roko-dual-source.yml.in >/dev/null
grep -F "10.101.101.125" installer/timebeat-roko-dual-source.yml.in >/dev/null
grep -F "concurrent_sources: 2" installer/timebeat-roko-dual-source.yml.in >/dev/null
grep -F "seats_to_offer: 0" installer/timebeat-roko-dual-source.yml.in >/dev/null
grep -F "adjust_clock: false" installer/timebeat-roko-dual-source.yml.in >/dev/null
! grep -Eq "66\.94\.104\.189|concurrent_sources:[[:space:]]*1|adjust_clock:[[:space:]]*true" installer/timebeat-roko-dual-source.yml.in

dry_run_output="$(
  NODE_NAME=smoke-observer NODE_ROLE=observer RUNTIME=native \
    SYNC_TIMEOUT_SECONDS=60 REPORT_PATH=/tmp/roko-smoke-readiness.txt \
    bin/roko-guided-install --time-stack chrony --non-interactive --dry-run
)"
grep -F "ROKO PTP²:      authenticated observer" <<<"$dry_run_output" >/dev/null
grep -F "Timebeat PTP²:  not selected" <<<"$dry_run_output" >/dev/null

timebeat_dry_run_output="$(
  NODE_NAME=smoke-validator NODE_ROLE=validator-candidate RUNTIME=native \
    SYNC_TIMEOUT_SECONDS=60 REPORT_PATH=/tmp/roko-smoke-readiness.txt \
    TIMEBEAT_PACKAGE=/secure/timebeat-2.3.5-amd64.deb \
    TIMEBEAT_LICENSE=/secure/timebeat.lic TIMEBEAT_INTERFACE=eth0 \
    bin/roko-guided-install --time-stack timebeat --non-interactive --dry-run
)"
grep -F "both managed OTA seeds with two concurrent sources" <<<"$timebeat_dry_run_output" >/dev/null

echo "smoke ok"
