#!/usr/bin/env bash
# Staged install/remove tests for bin/roko-stratum1-schedule (no systemctl, fake chronyc).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
subject="$here/../bin/roko-stratum1-schedule"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"
printf '#!/bin/sh\nexit 0\n' >"$work/bin/chronyc"; chmod +x "$work/bin/chronyc"
root="$work/root"
run() { env PATH="$work/bin:$PATH" ROKO_STRATUM1_DEST_ROOT="$root" "$subject" "$@"; }

run >"$work/dry.txt"
grep -F "dry run: nothing changed" "$work/dry.txt" >/dev/null
test ! -e "$root"

run --execute >/dev/null
test -x "$root/usr/local/libexec/roko-stratum1-bootstrap"
grep -E '^User=(_chrony|chrony|root)$' "$root/etc/systemd/system/roko-stratum1-bootstrap.service" >/dev/null
! grep -F '@CHRONY_USER@' "$root/etc/systemd/system/roko-stratum1-bootstrap.service"
grep -F 'FixedRandomDelay=true' "$root/etc/systemd/system/roko-stratum1-bootstrap.timer" >/dev/null
run --execute >/dev/null   # re-running over our own unit is allowed

run --cron --execute >/dev/null
grep -E '^[0-9]{1,2} \* \* \* \* (_chrony|chrony|root) /usr/local/libexec/roko-stratum1-bootstrap' \
  "$root/etc/cron.d/roko-stratum1-bootstrap" >/dev/null
minute1="$(cut -d' ' -f1 <"$root/etc/cron.d/roko-stratum1-bootstrap" | tail -1)"
run --cron --execute >/dev/null
test "$minute1" = "$(cut -d' ' -f1 <"$root/etc/cron.d/roko-stratum1-bootstrap" | tail -1)"

run --remove --execute >/dev/null
test ! -e "$root/usr/local/libexec/roko-stratum1-bootstrap"
test ! -e "$root/etc/systemd/system/roko-stratum1-bootstrap.service"
test ! -e "$root/etc/cron.d/roko-stratum1-bootstrap"

mkdir -p "$root/etc/systemd/system"
printf '[Service]\nExecStart=/usr/local/libexec/roko-stratum1-bootstrap\n' >"$root/etc/systemd/system/roko-stratum1-bootstrap.service"
if run --execute >/dev/null 2>&1; then echo "FAIL foreign unit was overwritten"; exit 1; fi
grep -qv 'roko-edge-tools' "$root/etc/systemd/system/roko-stratum1-bootstrap.service"

if run --bogus >/dev/null 2>&1; then echo "FAIL unknown option accepted"; exit 1; fi
echo "stratum1 schedule: ok"
