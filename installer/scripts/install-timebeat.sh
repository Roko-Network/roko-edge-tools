#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

: "${TIMEBEAT_PACKAGE:?TIMEBEAT_PACKAGE is required for the Timebeat profile}"
: "${TIMEBEAT_LICENSE:?TIMEBEAT_LICENSE is required for the Timebeat profile}"
: "${TIMEBEAT_CONFIG:?TIMEBEAT_CONFIG is required for the Timebeat profile}"

for input_file in "$TIMEBEAT_PACKAGE" "$TIMEBEAT_LICENSE" "$TIMEBEAT_CONFIG"; do
  [[ -f "$input_file" ]] || fail "Required operator-supplied Timebeat file not found: $input_file"
done
grep -qi 'ptpsquared' "$TIMEBEAT_CONFIG" ||
  fail "The reviewed Timebeat configuration must include a PTP Squared section."

case "$(uname -m)" in
  x86_64) expected_sha=b62701ca64ddb75193116ab94af0af831c9bde516322db00809db4fc287a49f0 ;;
  aarch64|arm64) expected_sha=d60e52c230817826649b3d0929d933746df432590b3972fd30afc1887f218be5 ;;
  *) fail "Timebeat 2.3.5 is supported here only on amd64 and arm64." ;;
esac
actual_sha="$(sha256sum "$TIMEBEAT_PACKAGE" | awk '{print $1}')"
[[ "$actual_sha" == "$expected_sha" ]] ||
  fail "Timebeat package checksum does not match the pinned 2.3.5 release for this architecture."

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
as_root install -o root -g root -m 0640 "$TIMEBEAT_CONFIG" /etc/timebeat/timebeat.yml
as_root install -d -o root -g root -m 0755 /etc/chrony/sources.d
regional_sources="$(mktemp)"
trap 'rm -f -- "$regional_sources"' EXIT
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/chrony-regional-sources.sh"
render_chrony_regional_sources >"$regional_sources"
as_root install -o root -g root -m 0644 \
  "$regional_sources" \
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

log "Verified Timebeat 2.3.5 installed with the operator-reviewed PTP Squared profile."
log "Chrony remains the clock owner; prove two independent sources before joining ROKO."
