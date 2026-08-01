#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

: "${TIMEBEAT_PACKAGE:?TIMEBEAT_PACKAGE is required for the Timebeat profile}"
: "${TIMEBEAT_LICENSE:?TIMEBEAT_LICENSE is required for the Timebeat profile}"
: "${TIMEBEAT_INTERFACE:?TIMEBEAT_INTERFACE is required for the Timebeat profile}"

for input_file in "$TIMEBEAT_PACKAGE" "$TIMEBEAT_LICENSE"; do
  [[ -f "$input_file" ]] || fail "Required operator-supplied Timebeat file not found: $input_file"
done
[[ "$TIMEBEAT_INTERFACE" =~ ^[A-Za-z0-9_.:-]{1,32}$ ]] || fail "Invalid Timebeat interface name."
[[ -d "/sys/class/net/$TIMEBEAT_INTERFACE" ]] || fail "Interface does not exist: $TIMEBEAT_INTERFACE"
for ota in 10.101.101.123 10.101.101.125; do
  timeout 5 bash -c "exec 3<>/dev/tcp/$ota/65107" 2>/dev/null ||
    fail "Cannot reach required OTA seed $ota on TCP/65107. No changes were made."
done

case "$(uname -m)" in
  x86_64) expected_sha=b62701ca64ddb75193116ab94af0af831c9bde516322db00809db4fc287a49f0 ;;
  aarch64|arm64) expected_sha=d60e52c230817826649b3d0929d933746df432590b3972fd30afc1887f218be5 ;;
  *) fail "Timebeat 2.3.5 is supported here only on amd64 and arm64." ;;
esac
actual_sha="$(sha256sum "$TIMEBEAT_PACKAGE" | awk '{print $1}')"
[[ "$actual_sha" == "$expected_sha" ]] ||
  fail "Timebeat package checksum does not match the pinned 2.3.5 release for this architecture."

template="$(dirname "${BASH_SOURCE[0]}")/../timebeat-roko-dual-source.yml.in"
[[ -f "$template" ]] || fail "Bundled ROKO dual-source Timebeat template is missing."
rendered_config="$(mktemp)"
trap 'rm -f -- "$rendered_config"' EXIT
sed "s/@TIMEBEAT_INTERFACE@/$TIMEBEAT_INTERFACE/g" "$template" >"$rendered_config"

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
  *) fail "Use the pinned vendor-provided Timebeat 2.3.5 .deb package." ;;
esac

as_root install -d -o root -g root -m 0750 /etc/timebeat
as_root install -o root -g root -m 0600 "$TIMEBEAT_LICENSE" /etc/timebeat/timebeat.lic
as_root install -o root -g root -m 0640 "$rendered_config" /etc/timebeat/timebeat.yml
as_root install -d -o root -g root -m 0755 /etc/chrony/sources.d
as_root install -o root -g root -m 0644 \
  "$(dirname "${BASH_SOURCE[0]}")/../roko-validator.sources" \
  /etc/chrony/sources.d/roko-validator.sources
if command -v apt-get >/dev/null 2>&1; then
  as_root apt-get update
  as_root apt-get install -y chrony
fi
as_root systemctl enable chrony.service
as_root systemctl restart chrony.service
as_root systemctl enable timebeat.service
as_root systemctl restart timebeat.service
systemctl is-active --quiet timebeat.service ||
  fail "Timebeat did not become active; inspect journalctl -u timebeat before continuing."

for conflicting_unit in ntp.service ntpd.service ptp4l.service; do
  if systemctl is-active --quiet "$conflicting_unit"; then
    fail "Conflicting clock-steering service remains active: $conflicting_unit"
  fi
done

log "Verified Timebeat 2.3.5 installed with the ROKO dual-OTA, two-source profile."
log "Chrony remains the clock owner; confirm both OTA sessions before validator activation."
