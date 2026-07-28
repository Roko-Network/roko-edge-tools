# ROKO Edge Tools

Small helper tools for people running ROKO local, edge, observer, or lab nodes.

This is the only public repository required by these optional diagnostics. The
node itself is distributed as either:

- an architecture-specific public image at
  `ghcr.io/roko-network/roko-node:testnet-latest-{amd64,arm64}`; or
- a checksum-verified native binary from
  [downloads.roko.network](https://downloads.roko.network/), also available
  through the [peer-assisted download guide](https://downloads.roko.network/torrent).

Node operation does not require access to the private source repository. See
[nodes.roko.network](https://nodes.roko.network/) for the current runbook.
The recommended setup path is to download the checksum manifest and reviewed
one-off scripts and their
[checksum manifest](https://downloads.roko.network/scripts/SHA256SUMS),
verify them locally, inspect them, and then run the native or Docker workflow.
Do not pipe a remote script directly into a shell. Offline Docker archives are
available by HTTPS and through the official torrent for registry-free setup.

The tools are intentionally dependency-light:

- Bash for host/service/time checks
- Python 3 standard library for JSON-RPC probes
- No secrets
- No writes unless you explicitly copy example config into your host

## Quick start

```bash
git clone https://github.com/Roko-Network/roko-edge-tools.git
cd roko-edge-tools

./bin/roko-edge-doctor
./bin/roko-rpc-health --rpc http://127.0.0.1:9944
./bin/roko-time-health
```

For a guided full, archive, observer, or validator-candidate installation:

```bash
./bin/roko-guided-install --time-stack chrony --dry-run
./bin/roko-guided-install --time-stack chrony
```

Operators using Timebeat can select `--time-stack timebeat`; they must obtain
their own package and per-node licence from
[timebeat.app](https://www.timebeat.app/downloads/software). The installer
collects the local package, licence, and reviewed configuration paths and
performs the remaining installation and verification steps. See the
[agentic installer guide](installer/README.md).

## Tools

| Tool | Purpose |
|---|---|
| `bin/roko-edge-doctor` | One-shot local node, service, RPC, disk, network, and Chrony health summary |
| `bin/roko-rpc-health` | JSON-RPC health probe for local or public ROKO RPC |
| `bin/roko-time-health` | Chrony/system clock diagnostics for NTP and edge time hosts |
| `bin/roko-node-tail` | Convenience log tail for a systemd-managed node |
| `bin/roko-edge-report` | Generate a sanitized support bundle |
| `bin/roko-seed-refresh` | Add current ROKO snapshot/release torrents to Transmission and verify completed payloads |
| `bin/roko-guided-install` | Run the self-contained AIWG-manifested installer for Chrony or operator-licensed Timebeat deployments |

## Common environment variables

```bash
export ROKO_RPC_URL=http://127.0.0.1:9944
export ROKO_SERVICE=roko-node
export ROKO_BASE_PATH=/var/lib/roko
export ROKO_NTP_SOURCE=ntp01.roko.network
export ROKO_SEED_DIR=/srv/roko-seed
export ROKO_SEED_PROFILES="normal releases"
```

## BitTorrent seeding

Seeders help distribute public snapshots and node release bundles. They do not
need validator keys, wallet material, private source access, or exposed RPC.

```bash
sudo install -d -o debian-transmission -g debian-transmission \
  /srv/roko-seed/snapshots /srv/roko-seed/releases
./bin/roko-seed-refresh
```

The default profiles seed the current normal snapshot and current node release
bundle. Add `archive` only when you have enough disk and bandwidth:

```bash
ROKO_SEED_PROFILES="normal archive releases" ./bin/roko-seed-refresh
```

For unattended refresh, install
`examples/roko-seed-refresh.service` and
`examples/roko-seed-refresh.timer` to `/etc/systemd/system/`, then enable the
timer. See the public guide at
[docs.roko.network](https://docs.roko.network/#bittorrent-seeding).

## Safety boundaries

- The guided observer flow inserts one ROKO `ptp2` key interactively; it never
  places the secret in argv, a manifest, or a report.
- The validator-candidate flow does not generate or manage validator session
  keys and never enables authoring.
- Timebeat software, configurations, and licences remain vendor/operator
  supplied and are never redistributed by ROKO.
- The installer performs the host, clock, ROKO runtime, service, observer-key,
  synchronization, finality, and readiness-report steps. It does not guess a
  vendor Timebeat configuration or activate validator authority.
- It does not expose RPC or NTP services.
- It does not change firewall rules.
- It does not delete old torrent data automatically.

Use it to observe and report; make operational changes deliberately.

## Mirrors

Primary public repo:

- `https://github.com/Roko-Network/roko-edge-tools`

Mirror:

- `https://git.integrolabs.net/roctinam/roko-edge-tools`
