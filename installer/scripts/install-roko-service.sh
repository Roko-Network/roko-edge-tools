#!/usr/bin/env bash
set -euo pipefail

runtime=""
node_name=""
archive=false
observer=false
clock_provider=chrony
start_service=false
dry_run=false
render_unit=false

usage() {
  cat <<'EOF'
Usage:
  install-roko-service.sh --runtime native|docker --node-name NAME
                          [--archive] [--observer]
                          [--clock-provider chrony|timebeat]
                          [--start] [--dry-run] [--render-unit]

Installs a hardened, non-authoring ROKO service with loopback-only Safe RPC.
Chrony deployments use the explicit node time-source contract. Docker mounts
the host command socket read/write and adds its numeric group to uid 1000.

--render-unit prints the deterministic unit instead of changing the host.
This script never generates keys, enrolls a validator, or enables authoring.
EOF
}

while (($#)); do
  case "$1" in
    --runtime) runtime="${2:-}"; shift ;;
    --node-name) node_name="${2:-}"; shift ;;
    --archive) archive=true ;;
    --observer) observer=true ;;
    --clock-provider) clock_provider="${2:-}"; shift ;;
    --start) start_service=true ;;
    --dry-run) dry_run=true ;;
    --render-unit) render_unit=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[[ "$runtime" == native || "$runtime" == docker ]] || {
  echo "--runtime must be native or docker" >&2; exit 2;
}
[[ "$clock_provider" == chrony || "$clock_provider" == timebeat ]] || {
  echo "--clock-provider must be chrony or timebeat" >&2; exit 2;
}
[[ "$node_name" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || {
  echo "--node-name must use 1-64 letters, digits, dots, underscores, or hyphens" >&2; exit 2;
}

chain_path=/etc/roko/roko-testnet-v2.json
data_path=/var/lib/roko
unit_path=/etc/systemd/system/roko-node.service
bootnode=/dns4/boot.roko.network/tcp/30333/ws/p2p/12D3KooWKSBZRtSiGKo8ueJtazCHT89LaBi6ZAtzgbeznf4NtVGj
chrony_socket=/run/chrony/chronyd.sock
pruning_line=""
"$archive" && pruning_line=$'  --pruning archive \\\n'
observer_line=""
"$observer" && observer_line=$'  --timesync-advertise-observer \\\n'

clock_unit=""
clock_gate=""
time_lines=""
chrony_gid=""
chrony_pre_line=""
chrony_mount_requirement=""
docker_chrony_lines=""
if [[ "$clock_provider" == chrony ]]; then
  clock_unit=chrony.service
  clock_gate="/usr/bin/chronyc waitsync 60 0.01"
  chrony_pre_line="ExecStartPre=/usr/bin/test -S $chrony_socket"
  chrony_mount_requirement=" /run/chrony"
  time_lines=$'  --timesync-time-source auto \\\n  --timesync-chrony-socket /run/chrony/chronyd.sock \\\n'
  if "$render_unit" || "$dry_run"; then
    chrony_gid="${ROKO_CHRONY_GID:-999}"
  else
    [[ -S "$chrony_socket" ]] || {
      echo "Missing Chrony command socket: $chrony_socket" >&2; exit 1;
    }
    chrony_gid="$(stat -c %g "$chrony_socket")"
    if systemctl cat chronyd.service >/dev/null 2>&1; then
      clock_unit=chronyd.service
    fi
  fi
  docker_chrony_lines=$'  --group-add '"$chrony_gid"$' \\\n  --mount type=bind,src=/run/chrony,dst=/run/chrony \\\n'
else
  clock_unit=timebeat.service
  clock_gate="/usr/bin/systemctl is-active --quiet timebeat.service"
fi

render_native_unit() {
  cat <<EOF
[Unit]
Description=ROKO full node
Wants=network-online.target
After=network-online.target $clock_unit
RequiresMountsFor=$data_path

[Service]
User=roko
Group=roko
$chrony_pre_line
ExecStartPre=$clock_gate
ExecStart=/usr/local/bin/roko-node \\
  --chain $chain_path \\
  --base-path $data_path \\
  --name $node_name \\
  --bootnodes $bootnode \\
  --port 30333 \\
  --rpc-port 9944 \\
${pruning_line}${time_lines}${observer_line}  --rpc-methods Safe
Restart=on-failure
RestartSec=10
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$data_path

[Install]
WantedBy=multi-user.target
EOF
}

render_docker_unit() {
  cat <<EOF
[Unit]
Description=ROKO full node (Docker)
Wants=network-online.target
After=network-online.target $clock_unit docker.service
Requires=docker.service
RequiresMountsFor=$data_path$chrony_mount_requirement

[Service]
EnvironmentFile=/etc/roko/node-image.env
$chrony_pre_line
ExecStartPre=$clock_gate
ExecStartPre=/usr/bin/docker run --rm --entrypoint /bin/sh \${ROKO_IMAGE} -ec 'test -x /usr/bin/chronyc && test -x /usr/sbin/ethtool && ! command -v chronyd >/dev/null 2>&1'
ExecStart=/usr/bin/docker run --rm --name roko-node --network host \\
${docker_chrony_lines}  --mount type=bind,src=$data_path,dst=/data \\
  --mount type=bind,src=$chain_path,dst=$chain_path,readonly \\
  \${ROKO_IMAGE} \\
  --database auto \\
  --chain $chain_path \\
  --base-path /data \\
  --name $node_name \\
  --bootnodes $bootnode \\
  --port 30333 \\
  --rpc-port 9944 \\
${pruning_line}${time_lines}${observer_line}  --rpc-methods Safe
ExecStop=/usr/bin/docker stop --time 60 roko-node
Restart=on-failure
RestartSec=10
TimeoutStopSec=75
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
}

if "$render_unit"; then
  if [[ "$runtime" == native ]]; then render_native_unit; else render_docker_unit; fi
  exit 0
fi

echo "ROKO service installation"
echo "  runtime: $runtime"
echo "  node name: $node_name"
echo "  archive: $archive"
echo "  observer: $observer"
echo "  clock provider: $clock_provider"
echo "  start now: $start_service"
if "$dry_run"; then exit 0; fi

[[ -f "$chain_path" ]] || {
  echo "Missing $chain_path; run bootstrap-roko-chain-spec.sh first." >&2; exit 1;
}
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
if [[ "$clock_provider" == timebeat ]]; then
  systemctl is-active --quiet timebeat.service || {
    echo "Timebeat must be configured, synchronized, and active." >&2; exit 1;
  }
else
  command -v chronyc >/dev/null || { echo "Chrony is required." >&2; exit 1; }
fi

task_tmp="$(mktemp)"
trap 'rm -f -- "$task_tmp"' EXIT
if [[ "$runtime" == native ]]; then
  [[ -x /usr/local/bin/roko-node ]] || { echo "Missing /usr/local/bin/roko-node." >&2; exit 1; }
  if ! getent passwd roko >/dev/null; then
    if [[ "$(id -u)" -eq 0 ]]; then
      useradd --system --home-dir "$data_path" --create-home --shell /usr/sbin/nologin roko
    else
      sudo useradd --system --home-dir "$data_path" --create-home --shell /usr/sbin/nologin roko
    fi
  fi
  if [[ "$clock_provider" == chrony ]]; then
    chrony_group="$(stat -c %G /run/chrony)"
    [[ "$chrony_group" != UNKNOWN ]] || { echo "Chrony runtime group has no local name." >&2; exit 1; }
    if [[ "$(id -u)" -eq 0 ]]; then usermod -a -G "$chrony_group" roko; else sudo usermod -a -G "$chrony_group" roko; fi
  fi
  render_native_unit >"$task_tmp"
  owner=roko; group=roko
else
  command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
  [[ -f /etc/roko/node-image.env ]] || { echo "Missing /etc/roko/node-image.env." >&2; exit 1; }
  # shellcheck disable=SC1091
  source /etc/roko/node-image.env
  [[ "${ROKO_IMAGE:-}" == sha256:* ]] || { echo "ROKO_IMAGE must be an immutable local image ID." >&2; exit 1; }
  docker run --rm --entrypoint /bin/sh "$ROKO_IMAGE" -ec \
    'test -x /usr/bin/chronyc && test -x /usr/sbin/ethtool && ! command -v chronyd >/dev/null 2>&1' || {
      echo "ROKO image lacks the supported host-Chrony validator contract; reinstall the current release image." >&2
      exit 1
    }
  render_docker_unit >"$task_tmp"
  owner=1000; group=1000
fi

if [[ "$(id -u)" -eq 0 ]]; then
  install -d -o "$owner" -g "$group" -m 0750 "$data_path"
  install -o root -g root -m 0644 "$task_tmp" "$unit_path"
  systemctl daemon-reload
  systemctl enable roko-node
  "$start_service" && systemctl restart roko-node
else
  sudo install -d -o "$owner" -g "$group" -m 0750 "$data_path"
  sudo install -o root -g root -m 0644 "$task_tmp" "$unit_path"
  sudo systemctl daemon-reload
  sudo systemctl enable roko-node
  "$start_service" && sudo systemctl restart roko-node
fi

echo "Installed $unit_path"
if ! "$start_service"; then
  echo "Run 'sudo systemctl start roko-node' after the selected clock provider is synchronized."
fi
