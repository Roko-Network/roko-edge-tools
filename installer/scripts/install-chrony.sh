#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

load_os_release

case "$ROKO_DISTRO $ROKO_DISTRO_LIKE" in
  *debian*|*ubuntu*)
    as_root apt-get update
    as_root apt-get install -y chrony
    chrony_config=/etc/chrony/chrony.conf
    chrony_unit=chrony.service
    ;;
  *fedora*|*rhel*|*centos*)
    if command -v dnf >/dev/null 2>&1; then
      as_root dnf install -y chrony
    else
      as_root yum install -y chrony
    fi
    chrony_config=/etc/chrony.conf
    chrony_unit=chronyd.service
    ;;
  *) fail "Unsupported distribution for automated Chrony installation: $ROKO_DISTRO" ;;
esac

[[ -f "$chrony_config" ]] || fail "Chrony installed without expected configuration: $chrony_config"
as_root install -d -o root -g root -m 0755 /etc/chrony/sources.d
task_source="$(mktemp)"
trap 'rm -f -- "$task_source"' EXIT
cat >"$task_source" <<'EOF'
# ROKO is one source, not the only source.
server time.roko.network iburst
pool pool.ntp.org iburst maxsources 3
EOF
as_root install -o root -g root -m 0644 "$task_source" /etc/chrony/sources.d/roko.sources

if ! grep -Eq '^[[:space:]]*sourcedir[[:space:]]+/etc/chrony/sources\.d([[:space:]]|$)' "$chrony_config"; then
  printf '\n# ROKO managed source drop-ins\nsourcedir /etc/chrony/sources.d\n' |
    as_root tee -a "$chrony_config" >/dev/null
fi

as_root systemctl enable "$chrony_unit"
as_root systemctl restart "$chrony_unit"
chronyc waitsync 60 0.01
chronyc tracking
chronyc sources -v
log "Chrony installed, configured with diverse sources, and synchronized."
