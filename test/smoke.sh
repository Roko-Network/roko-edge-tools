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

echo "smoke ok"
