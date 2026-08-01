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
python3 test/docset.py

grep -R "ntp01.roko.network" README.md examples docs bin lib >/dev/null
grep -R "/roko/timesync/1" README.md docs >/dev/null
grep -R "bittorrent-seeding" README.md examples bin >/dev/null
grep -R "setup.aiwg.io/v1" installer/*.yaml >/dev/null
grep -R "www.timebeat.app/downloads/software" README.md installer >/dev/null
grep -R "redistribut" README.md installer >/dev/null
grep -F "wait for explicit operator approval" installer/AGENT-INSTALL.md >/dev/null
grep -F "Do not include secrets" installer/AGENT-INSTALL.md >/dev/null
grep -F "ROKO chain P2P: enabled via the public bootnode" bin/roko-guided-install >/dev/null
grep -F "temporal_getMeshState" installer/scripts/start-and-verify.sh >/dev/null
grep -F "roko_ptp2_mode=" installer/scripts/write-readiness-report.sh >/dev/null
grep -F "schema: aiwg.pagenbar.docset/v1" docs/time-authority/docset.yaml >/dev/null
for page in docs/time-authority/*.md; do
  grep -F "Pagenbar:" "$page" >/dev/null
  grep -F "last_reviewed:" "$page" >/dev/null
done
grep -F "time-a-g.nist.gov" installer/scripts/chrony-regional-sources.sh >/dev/null
grep -F "ptbtime4.ptb.de" installer/scripts/chrony-regional-sources.sh >/dev/null
grep -F "ntp.nict.jp" installer/scripts/chrony-regional-sources.sh >/dev/null
grep -F "minsources 2" installer/scripts/chrony-regional-sources.sh >/dev/null

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
    TIMEBEAT_LICENSE=/secure/timebeat.lic TIMEBEAT_CONFIG=/secure/timebeat.yml \
    TIME_REGION=global \
    bin/roko-guided-install --time-stack timebeat --non-interactive --dry-run
)"
grep -F "operator-reviewed public or self-operated PTP2 authority profile" <<<"$timebeat_dry_run_output" >/dev/null

echo "smoke ok"
