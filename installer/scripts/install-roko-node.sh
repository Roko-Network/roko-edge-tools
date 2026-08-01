#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

validate_common_params
scripts_base="${ROKO_SCRIPTS_BASE:-https://downloads.roko.network/scripts}"
task_dir="$(mktemp -d)"
trap 'rm -rf -- "$task_dir"' EXIT

script_names=(
  install-roko-native.sh
  install-roko-docker.sh
  bootstrap-roko-chain-spec.sh
  install-roko-service.sh
)
for filename in SHA256SUMS "${script_names[@]}"; do
  curl --fail --location --silent --show-error "$scripts_base/$filename" --output "$task_dir/$filename"
done
(
  cd "$task_dir"
  sha256sum --check --ignore-missing SHA256SUMS
  for filename in "${script_names[@]}"; do bash -n "$filename"; done
)

if [[ "$RUNTIME" == native ]]; then
  bash "$task_dir/install-roko-native.sh"
else
  bash "$task_dir/install-roko-docker.sh"
fi
bash "$task_dir/bootstrap-roko-chain-spec.sh"

service_args=(--runtime "$RUNTIME" --node-name "$NODE_NAME" --clock-provider "${CLOCK_PROVIDER:-chrony}")
[[ "$NODE_ROLE" == archive ]] && service_args+=(--archive)
[[ "$NODE_ROLE" == observer ]] && service_args+=(--observer)
bash "$task_dir/install-roko-service.sh" "${service_args[@]}"
log "Installed the verified ROKO node and non-authoring service profile."
