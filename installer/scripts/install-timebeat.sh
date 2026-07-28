#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

: "${TIMEBEAT_PACKAGE:?TIMEBEAT_PACKAGE is required for the Timebeat profile}"
: "${TIMEBEAT_LICENSE:?TIMEBEAT_LICENSE is required for the Timebeat profile}"
: "${TIMEBEAT_CONFIG:?TIMEBEAT_CONFIG is required for the Timebeat profile}"

for input_file in "$TIMEBEAT_PACKAGE" "$TIMEBEAT_LICENSE" "$TIMEBEAT_CONFIG"; do
  [[ -f "$input_file" ]] || fail "Required operator-supplied Timebeat file not found: $input_file"
done

grep -qi 'ptpsquared' "$TIMEBEAT_CONFIG" ||
  fail "The reviewed Timebeat configuration must include the vendor PTP² Mesh section."

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -f /etc/timebeat/timebeat.yml ]]; then
  as_root cp -a /etc/timebeat/timebeat.yml "/etc/timebeat/timebeat.yml.pre-roko-${timestamp}"
fi
if [[ -f /etc/timebeat/timebeat.lic ]]; then
  as_root cp -a /etc/timebeat/timebeat.lic "/etc/timebeat/timebeat.lic.pre-roko-${timestamp}"
fi

load_os_release
case "$TIMEBEAT_PACKAGE" in
  *.deb)
    case "$ROKO_DISTRO $ROKO_DISTRO_LIKE" in
      *debian*|*ubuntu*) as_root apt-get install -y "$TIMEBEAT_PACKAGE" ;;
      *) fail "A .deb Timebeat package requires Debian or Ubuntu." ;;
    esac
    ;;
  *.rpm)
    case "$ROKO_DISTRO $ROKO_DISTRO_LIKE" in
      *fedora*|*rhel*|*centos*)
        if command -v dnf >/dev/null 2>&1; then
          as_root dnf install -y "$TIMEBEAT_PACKAGE"
        else
          as_root yum install -y "$TIMEBEAT_PACKAGE"
        fi
        ;;
      *) fail "An .rpm Timebeat package requires Fedora or RHEL-family Linux." ;;
    esac
    ;;
  *) fail "Use the vendor-provided .deb or .rpm Timebeat Agent package." ;;
esac

as_root install -d -o root -g root -m 0750 /etc/timebeat
as_root install -o root -g root -m 0600 "$TIMEBEAT_LICENSE" /etc/timebeat/timebeat.lic
as_root install -o root -g root -m 0640 "$TIMEBEAT_CONFIG" /etc/timebeat/timebeat.yml
as_root systemctl enable timebeat.service
as_root systemctl restart timebeat.service
systemctl is-active --quiet timebeat.service ||
  fail "Timebeat did not become active; inspect journalctl -u timebeat before continuing."

for conflicting_unit in chrony.service chronyd.service ntp.service ntpd.service ptp4l.service; do
  if systemctl is-active --quiet "$conflicting_unit"; then
    fail "Conflicting clock-steering service remains active: $conflicting_unit"
  fi
done

log "Operator-licensed Timebeat Agent installed with the supplied reviewed configuration."
log "Confirm vendor PTP² Mesh convergence before relying on this host for validator timing."
