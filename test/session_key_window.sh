#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
fake_bin="$temporary/bin"
mkdir -p "$fake_bin"

cat >"$fake_bin/id" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -u ]] && printf '0\n'
EOF

cat >"$fake_bin/stat" <<'EOF'
#!/usr/bin/env bash
case "${2:-}" in
  %u|"'%u'") printf '0\n' ;;
  %a|"'%a'") printf '600\n' ;;
  *) /usr/bin/stat "$@" ;;
esac
EOF

cat >"$fake_bin/systemctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  cat)
    cat <<UNIT
[Service]
Environment=ROKO_RPC_METHODS=Safe
EnvironmentFile=-${KEY_WINDOW_POLICY}
ExecStart=/usr/local/bin/roko-node --rpc-methods \${ROKO_RPC_METHODS}${KEY_WINDOW_PUBLIC_FLAG:-}
UNIT
    ;;
  is-active) exit 0 ;;
  restart)
    printf 'restart\n' >>"${KEY_WINDOW_EVENTS}"
    if [[ "$(tr -d '\r\n' <"${KEY_WINDOW_POLICY}")" == ROKO_RPC_METHODS=Safe && -e "${KEY_WINDOW_FAIL_RESTORE}" ]]; then
      exit 1
    fi
    ;;
  stop) printf 'stop\n' >>"${KEY_WINDOW_EVENTS}" ;;
  *) exit 1 ;;
esac
EOF

cat >"$fake_bin/roko-validator-enroll" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
check=false
generate=false
isolated=false
output=""
while (($#)); do
  case "$1" in
    --check-rpc-policy) check=true ;;
    --confirm-new-keys) generate=true ;;
    --confirm-isolated-unsafe-rpc) isolated=true ;;
    --output) output="${2:-}"; shift ;;
  esac
  shift
done
mode="$(tr -d '\r\n' <"${KEY_WINDOW_POLICY}")"
if "$check"; then
  [[ "$mode" == ROKO_RPC_METHODS=Safe ]] && exit 0
  exit 2
fi
"$generate" && "$isolated" && [[ "$mode" == ROKO_RPC_METHODS=Unsafe ]] || exit 9
printf 'generated\n' >>"${KEY_WINDOW_EVENTS}"
[[ -z "$output" ]] || printf '{}\n' >"$output"
[[ "${KEY_WINDOW_GENERATE_FAIL:-0}" == 0 ]] || exit 7
EOF

chmod +x "$fake_bin/id" "$fake_bin/stat" "$fake_bin/systemctl" "$fake_bin/roko-validator-enroll"

run_case() {
  local name="$1"
  case_root="$temporary/$name"
  mkdir -p "$case_root"
  export KEY_WINDOW_POLICY="$case_root/node-rpc.env"
  export KEY_WINDOW_EVENTS="$case_root/events"
  export KEY_WINDOW_FAIL_RESTORE="$case_root/fail-restore"
  : >"$KEY_WINDOW_EVENTS"
  printf 'ROKO_RPC_METHODS=Safe\n' >"$KEY_WINDOW_POLICY"
  PATH="$fake_bin:/usr/bin:/bin" ROKO_KEY_WINDOW_WAIT_ATTEMPTS=1 \
    "$root/bin/roko-session-key-window" \
    --policy-file "$KEY_WINDOW_POLICY" \
    --enroll-command "$fake_bin/roko-validator-enroll" \
    --confirm-isolated-window --confirm-no-forwarding -- \
    --binary /usr/local/bin/roko-node \
    --public-address /dns4/validator.example/tcp/30333/p2p/TEST \
    --output "$case_root/enrollment.json"
}

run_case success
grep -Fx 'ROKO_RPC_METHODS=Safe' "$KEY_WINDOW_POLICY" >/dev/null
[[ "$(grep -c '^restart$' "$KEY_WINDOW_EVENTS")" == 2 ]]
grep -Fx generated "$KEY_WINDOW_EVENTS" >/dev/null
[[ -f "$case_root/enrollment.json" ]]
[[ "$(find "$case_root" -maxdepth 1 -name 'node-rpc.env.before-session-key-window-*' | wc -l)" == 1 ]]

set +e
KEY_WINDOW_GENERATE_FAIL=1 run_case generation-failure >/dev/null 2>&1
generation_rc=$?
set -e
[[ "$generation_rc" == 7 ]]
grep -Fx 'ROKO_RPC_METHODS=Safe' "$KEY_WINDOW_POLICY" >/dev/null
[[ "$(grep -c '^restart$' "$KEY_WINDOW_EVENTS")" == 2 ]]

set +e
case_root="$temporary/public-listener"
mkdir -p "$case_root"
export KEY_WINDOW_POLICY="$case_root/node-rpc.env"
export KEY_WINDOW_EVENTS="$case_root/events"
export KEY_WINDOW_FAIL_RESTORE="$case_root/fail-restore"
printf 'ROKO_RPC_METHODS=Safe\n' >"$KEY_WINDOW_POLICY"
: >"$KEY_WINDOW_EVENTS"
KEY_WINDOW_PUBLIC_FLAG=' --rpc-external' PATH="$fake_bin:/usr/bin:/bin" \
  "$root/bin/roko-session-key-window" --policy-file "$KEY_WINDOW_POLICY" \
  --enroll-command "$fake_bin/roko-validator-enroll" \
  --confirm-isolated-window --confirm-no-forwarding -- \
  --output "$case_root/enrollment.json" >/dev/null 2>&1
public_rc=$?
set -e
[[ "$public_rc" == 1 ]]
[[ ! -s "$KEY_WINDOW_EVENTS" ]]

set +e
case_root="$temporary/restore-failure"
mkdir -p "$case_root"
export KEY_WINDOW_POLICY="$case_root/node-rpc.env"
export KEY_WINDOW_EVENTS="$case_root/events"
export KEY_WINDOW_FAIL_RESTORE="$case_root/fail-restore"
printf 'ROKO_RPC_METHODS=Safe\n' >"$KEY_WINDOW_POLICY"
: >"$KEY_WINDOW_EVENTS"
# The fake enrollment command marks generation; make the Safe restart fail
# after generation by wrapping systemctl's marker check through the event file.
cat >"$fake_bin/systemctl-restore-failure" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  cat)
    printf '[Service]\nEnvironment=ROKO_RPC_METHODS=Safe\nEnvironmentFile=-%s\nExecStart=/usr/local/bin/roko-node --rpc-methods ${ROKO_RPC_METHODS}\n' "$KEY_WINDOW_POLICY"
    ;;
  is-active) exit 0 ;;
  restart)
    printf 'restart\n' >>"$KEY_WINDOW_EVENTS"
    if grep -Fx generated "$KEY_WINDOW_EVENTS" >/dev/null && [[ "$(tr -d '\r\n' <"$KEY_WINDOW_POLICY")" == ROKO_RPC_METHODS=Safe ]]; then exit 1; fi
    ;;
  stop) printf 'stop\n' >>"$KEY_WINDOW_EVENTS" ;;
esac
EOF
chmod +x "$fake_bin/systemctl-restore-failure"
mv "$fake_bin/systemctl" "$fake_bin/systemctl-normal"
cp "$fake_bin/systemctl-restore-failure" "$fake_bin/systemctl"
PATH="$fake_bin:/usr/bin:/bin" ROKO_KEY_WINDOW_WAIT_ATTEMPTS=1 \
  "$root/bin/roko-session-key-window" --policy-file "$KEY_WINDOW_POLICY" \
  --enroll-command "$fake_bin/roko-validator-enroll" \
  --confirm-isolated-window --confirm-no-forwarding -- \
  --output "$case_root/enrollment.json" >/dev/null 2>&1
restore_rc=$?
mv "$fake_bin/systemctl-normal" "$fake_bin/systemctl"
set -e
[[ "$restore_rc" == 1 ]]
grep -Fx 'ROKO_RPC_METHODS=Safe' "$KEY_WINDOW_POLICY" >/dev/null
grep -Fx stop "$KEY_WINDOW_EVENTS" >/dev/null

printf '%s\n' "session key window tests ok"
