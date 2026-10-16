#!/usr/bin/env bash
# Rendered service units must satisfy the roko-session-key-window RPC policy contract.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
installer="$root/installer/scripts/install-roko-service.sh"
temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
fake_bin="$temporary/bin"
mkdir -p "$fake_bin"
peer=12D3KooWKSBZRtSiGKo8ueJtazCHT89LaBi6ZAtzgbeznf4NtVGj
export ROKO_CHRONY_GID=104
export ROKO_AUTHORITY_ADDRESSES="/dns4/a.example/tcp/30333/p2p/$peer
/dns4/b.example/tcp/30333/p2p/$peer"

cat >"$fake_bin/id" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -u ]] && printf '0\n'
EOF
cat >"$fake_bin/stat" <<'EOF'
#!/usr/bin/env bash
case "${2:-}" in
  %u) printf '0\n' ;;
  %a) printf '600\n' ;;
  *) /usr/bin/stat "$@" ;;
esac
EOF
cat >"$fake_bin/systemctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  cat) sed "s#/etc/roko/node-rpc.env#${KEY_WINDOW_POLICY}#g" "$RENDERED_UNIT" ;;
  is-active|restart|stop) printf '%s\n' "$1" >>"$KEY_WINDOW_EVENTS" ;;
  *) exit 1 ;;
esac
EOF
cat >"$fake_bin/roko-validator-enroll" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
mode="$(tr -d '\r\n' <"$KEY_WINDOW_POLICY")"
case " $* " in
  *" --check-rpc-policy "*) [[ "$mode" == ROKO_RPC_METHODS=Safe ]] && exit 0; exit 2 ;;
esac
[[ "$mode" == ROKO_RPC_METHODS=Unsafe ]] || exit 9
printf 'generated\n' >>"$KEY_WINDOW_EVENTS"
EOF
chmod +x "$fake_bin"/*

for runtime in native docker; do
  for role in validator full observer; do
    case "$role" in
      validator) role_args=(--validator-candidate) ;;
      observer) role_args=(--observer) ;;
      *) role_args=() ;;
    esac
    case_root="$temporary/$runtime-$role"
    mkdir -p "$case_root"
    export RENDERED_UNIT="$case_root/roko-node.service"
    export KEY_WINDOW_POLICY="$case_root/node-rpc.env"
    export KEY_WINDOW_EVENTS="$case_root/events"
    "$installer" --runtime "$runtime" --node-name fixture --render-unit "${role_args[@]}" >"$RENDERED_UNIT"
    if grep -F -- '--rpc-methods Safe' "$RENDERED_UNIT" >/dev/null; then
      echo "$runtime/$role unit still hardcodes --rpc-methods Safe" >&2; exit 1
    fi
    grep -Fx 'Environment=ROKO_RPC_METHODS=Safe' "$RENDERED_UNIT" >/dev/null
    grep -Fx 'EnvironmentFile=-/etc/roko/node-rpc.env' "$RENDERED_UNIT" >/dev/null
    printf 'ROKO_RPC_METHODS=Safe\n' >"$KEY_WINDOW_POLICY"
    : >"$KEY_WINDOW_EVENTS"
    PATH="$fake_bin:/usr/bin:/bin" ROKO_KEY_WINDOW_WAIT_ATTEMPTS=1 \
      "$root/bin/roko-session-key-window" \
      --policy-file "$KEY_WINDOW_POLICY" \
      --enroll-command "$fake_bin/roko-validator-enroll" \
      --confirm-isolated-window --confirm-no-forwarding -- \
      --binary /usr/local/bin/roko-node --output "$case_root/enrollment.json" >/dev/null
    grep -Fx generated "$KEY_WINDOW_EVENTS" >/dev/null
    grep -Fx 'ROKO_RPC_METHODS=Safe' "$KEY_WINDOW_POLICY" >/dev/null
  done
done

# Install-time policy handling: create when absent, keep exact Safe, refuse anything else.
as_root() { "$@"; }
eval "$(sed -n '/^ensure_rpc_policy() {$/,/^}$/p' "$installer")"
install() {
  local mode="" args=()
  while (($#)); do
    case "$1" in
      -D) ;;
      -o|-g) shift ;;
      -m) mode="$2"; shift ;;
      *) args+=("$1") ;;
    esac
    shift
  done
  mkdir -p "$(dirname "${args[1]}")"
  cp -- "${args[0]}" "${args[1]}"
  chmod "$mode" "${args[1]}"
}
stat() {
  if [[ "${2:-}" == %u ]]; then printf '0\n'; else command stat "$@"; fi
}

policy="$temporary/etc/roko/node-rpc.env"
ensure_rpc_policy "$policy"
[[ "$(cat "$policy")" == ROKO_RPC_METHODS=Safe ]]
[[ "$(command stat -c %a "$policy")" == 600 ]]
ensure_rpc_policy "$policy"

printf 'ROKO_RPC_METHODS=Unsafe\n' >"$policy"
if ensure_rpc_policy "$policy" 2>/dev/null; then
  echo "installer accepted an Unsafe policy file" >&2; exit 1
fi
printf 'ROKO_RPC_METHODS=Safe\n' >"$policy"
chmod 0666 "$policy"
if ensure_rpc_policy "$policy" 2>/dev/null; then
  echo "installer accepted a world-writable policy file" >&2; exit 1
fi
rm -f -- "$policy"
ln -s "$temporary/elsewhere" "$policy"
if ensure_rpc_policy "$policy" 2>/dev/null; then
  echo "installer accepted a symlinked policy file" >&2; exit 1
fi

echo "service rpc policy contract ok"
