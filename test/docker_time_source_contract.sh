#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="$root/installer/scripts/install-roko-service.sh"

docker_unit="$(ROKO_CHRONY_GID=104 "$service" \
  --runtime docker --node-name fixture-validator --clock-provider chrony --render-unit)"
grep -F -- '--group-add 104' <<<"$docker_unit" >/dev/null
grep -F -- '--mount type=bind,src=/run/chrony,dst=/run/chrony' <<<"$docker_unit" >/dev/null
grep -F -- '--timesync-time-source auto' <<<"$docker_unit" >/dev/null
grep -F -- '--timesync-chrony-socket /run/chrony/chronyd.sock' <<<"$docker_unit" >/dev/null
grep -F -- 'test -x /usr/bin/chronyc' <<<"$docker_unit" >/dev/null
grep -F -- '! command -v chronyd' <<<"$docker_unit" >/dev/null
if grep -F -- '--validator' <<<"$docker_unit" >/dev/null; then
  echo "Docker candidate unit unexpectedly enables validator authoring" >&2
  exit 1
fi

native_unit="$(ROKO_CHRONY_GID=104 "$service" \
  --runtime native --node-name fixture-validator --clock-provider chrony --render-unit)"
grep -F -- '--timesync-time-source auto' <<<"$native_unit" >/dev/null
grep -F -- '--timesync-chrony-socket /run/chrony/chronyd.sock' <<<"$native_unit" >/dev/null
if grep -F -- '--validator' <<<"$native_unit" >/dev/null; then
  echo "Native candidate unit unexpectedly enables validator authoring" >&2
  exit 1
fi

grep -F "roko-node-testnet-docker-\${roko_arch}.tar.gz" \
  "$root/installer/scripts/install-roko-docker.sh" >/dev/null
grep -F 'org.opencontainers.image.revision' \
  "$root/installer/scripts/install-roko-docker.sh" >/dev/null
grep -F 'sha256sum --check' "$root/installer/scripts/install-roko-docker.sh" >/dev/null

echo "docker time-source contract ok"
