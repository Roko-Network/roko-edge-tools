#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="$root/installer/scripts/install-roko-service.sh"
tmpdir="$(mktemp -d)"
trap 'rm -rf -- "$tmpdir"' EXIT

cat >"$tmpdir/id" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  -u) printf '1000\n' ;;
  -un) printf 'fixture\n' ;;
  *) /usr/bin/id "$@" ;;
esac
EOF

cat >"$tmpdir/sudo" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${SUDO_LOG:?}"
if [[ "${1:-}" == -n ]]; then
  shift
fi
case "${1:-}" in
  true)
    exit 0
    ;;
  test)
    [[ "${2:-}" == -S && "${3:-}" == /run/chrony/chronyd.sock ]]
    [[ "${ROKO_TEST_CHRONY_SOCKET_STATE:-present}" == present ]]
    ;;
  stat)
    [[ "${2:-}" == -c && "${3:-}" == %g && "${4:-}" == /run/chrony/chronyd.sock ]]
    [[ "${ROKO_TEST_CHRONY_SOCKET_STATE:-present}" == present ]]
    printf '104\n'
    ;;
  *)
    printf 'unexpected sudo command: %s\n' "$*" >&2
    exit 99
    ;;
esac
EOF

cat >"$tmpdir/stat" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'direct stat should not be used by non-root socket check: %s\n' "$*" >&2
exit 99
EOF

cat >"$tmpdir/systemctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 1
EOF

chmod +x "$tmpdir/id" "$tmpdir/sudo" "$tmpdir/stat" "$tmpdir/systemctl"

sudo_log="$tmpdir/sudo.log"
output="$tmpdir/output.txt"

SUDO_LOG="$sudo_log" PATH="$tmpdir:$PATH" ROKO_TEST_CHRONY_SOCKET_STATE=present \
  "$service" --runtime docker --node-name fixture-validator --clock-provider chrony --dry-run \
  >"$output"
grep -F "ROKO service installation" "$output" >/dev/null
grep -F -- "-n test -S /run/chrony/chronyd.sock" "$sudo_log" >/dev/null
grep -F -- "-n stat -c %g /run/chrony/chronyd.sock" "$sudo_log" >/dev/null

if SUDO_LOG="$sudo_log" PATH="$tmpdir:$PATH" ROKO_TEST_CHRONY_SOCKET_STATE=missing \
  "$service" --runtime docker --node-name fixture-validator --clock-provider chrony --dry-run \
  >"$tmpdir/missing.out" 2>"$tmpdir/missing.err"; then
  echo "missing Chrony socket unexpectedly passed" >&2
  exit 1
fi
grep -F "Missing Chrony command socket: /run/chrony/chronyd.sock (checked as root via sudo from fixture)." \
  "$tmpdir/missing.err" >/dev/null
grep -F "If sudo escalation is unavailable, run this installer with sudo." \
  "$tmpdir/missing.err" >/dev/null

cat >"$tmpdir/sudo" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${SUDO_LOG:?}"
if [[ "${1:-}" == -n && "${2:-}" == true ]]; then
  exit 1
fi
printf 'unexpected sudo command after failed sudo -n true: %s\n' "$*" >&2
exit 99
EOF
chmod +x "$tmpdir/sudo"
: >"$sudo_log"

SUDO_LOG="$sudo_log" PATH="$tmpdir:$PATH" \
  "$service" --runtime docker --node-name fixture-validator --clock-provider chrony --dry-run \
  >"$tmpdir/dry-run-no-sudo.out" 2>"$tmpdir/dry-run-no-sudo.err"
grep -F "ROKO service installation" "$tmpdir/dry-run-no-sudo.out" >/dev/null
grep -F "Warning: could not check Chrony command socket during dry run because non-interactive sudo is unavailable" \
  "$tmpdir/dry-run-no-sudo.err" >/dev/null
test "$(wc -l <"$sudo_log")" -eq 1

echo "chrony socket contract ok"
