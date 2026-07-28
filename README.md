<p align="center">
  <a href="https://nodes.roko.network/edge/">
    <img src="assets/roko-logo.png" width="104" height="104" alt="ROKO Network">
  </a>
</p>

<h1 align="center">ROKO Edge Tools</h1>

<p align="center">
  Operator-first health, diagnostics, and reporting tools for infrastructure you control.
</p>

<p align="center">
  <a href="https://nodes.roko.network/edge/">Edge guide</a>
  ·
  <a href="https://time.roko.network/">ROKO Time</a>
  ·
  <a href="https://docs.roko.network/">Documentation</a>
</p>

---

ROKO Edge Tools is the dependency-light companion for local, edge, observer,
and lab nodes. The toolkit inspects your host and reports what it sees; it does
not silently change network, validator, or time configuration.

## Design principles

- Bash for host/service/time checks
- Python 3 standard library for JSON-RPC probes
- No secret collection
- No configuration writes unless you explicitly copy the example yourself
- Local RPC by default

## Quick start

```bash
git clone https://github.com/Roko-Network/roko-edge-tools.git
cd roko-edge-tools

./bin/roko-edge-doctor
./bin/roko-rpc-health --rpc http://127.0.0.1:9944
./bin/roko-time-health
```

## Included tools

| Tool | Purpose |
|:---|:---|
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

## Safety boundary

- It does not manage validator keys.
- It does not insert PTP² keys.
- It does not expose RPC or NTP services.
- It does not change firewall rules.

Use it to observe and report; make operational changes deliberately.

Read the [edge operator notes](docs/edge-operator-notes.md) before exposing
services beyond loopback or a private LAN.

## Mirrors

- Primary: [github.com/Roko-Network/roko-edge-tools](https://github.com/Roko-Network/roko-edge-tools)
- Mirror: [git.integrolabs.net/roctinam/roko-edge-tools](https://git.integrolabs.net/roctinam/roko-edge-tools)
