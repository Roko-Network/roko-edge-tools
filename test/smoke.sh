#!/usr/bin/env bash
set -euo pipefail

bash -n lib/roko-edge-common.sh
bash -n bin/roko-edge-doctor
bash -n bin/roko-time-health
bash -n bin/roko-node-tail
bash -n bin/roko-edge-report
python3 -m py_compile bin/roko-rpc-health

grep -R "ntp01.roko.network" README.md examples docs bin lib >/dev/null
grep -R "/roko/timesync/1" README.md docs >/dev/null

echo "smoke ok"
