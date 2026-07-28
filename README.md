# ROKO Edge Tools

Small helper tools for people running ROKO local, edge, observer, or lab nodes.

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
