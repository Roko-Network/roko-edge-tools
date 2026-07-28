# ROKO Edge Tools

Small helper tools for people running ROKO local, edge, observer, or lab nodes.

This is the only public repository required by these optional diagnostics. The
node itself is distributed as either:

- an architecture-specific public image at
  `ghcr.io/roko-network/roko-node:testnet-latest-{amd64,arm64}`; or
- a checksum-verified native binary from
  [downloads.roko.network](https://downloads.roko.network/), also available
  through [torrent.roko.network](https://torrent.roko.network/).

Node operation does not require access to the private source repository. See
[nodes.roko.network](https://nodes.roko.network/) for the current runbook.

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

## Tools

| Tool | Purpose |
|---|---|
| `bin/roko-edge-doctor` | One-shot local node, service, RPC, disk, network, and Chrony health summary |
| `bin/roko-rpc-health` | JSON-RPC health probe for local or public ROKO RPC |
| `bin/roko-time-health` | Chrony/system clock diagnostics for NTP and edge time hosts |
| `bin/roko-node-tail` | Convenience log tail for a systemd-managed node |
| `bin/roko-edge-report` | Generate a sanitized support bundle |

## Common environment variables

```bash
export ROKO_RPC_URL=http://127.0.0.1:9944
export ROKO_SERVICE=roko-node
export ROKO_BASE_PATH=/var/lib/roko
export ROKO_NTP_SOURCE=ntp01.roko.network
```

## What this does not do

- It does not manage validator keys.
- It does not insert PTP² keys.
- It does not expose RPC or NTP services.
- It does not change firewall rules.

Use it to observe and report; make operational changes deliberately.

## Mirrors

Primary public repo:

- `https://github.com/Roko-Network/roko-edge-tools`

Mirror:

- `https://git.integrolabs.net/roctinam/roko-edge-tools`
