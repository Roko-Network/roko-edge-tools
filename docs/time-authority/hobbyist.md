---
id: roko-time-authority.hobbyist
title: Hobbyist deployment
summary: Safe guided setup for a home, lab, edge, or observer node.
audience: [hobbyist, agent]
tasks: [install, verify, maintain]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Installing a non-authoring node on a conventional Linux host.
previous: choose-sources.md
next: professional.md
---

# Hobbyist deployment

Use wired networking when possible, keep RPC loopback-only, and let the guided
installer configure a regional Chrony profile before starting ROKO.

```bash
git clone https://github.com/Roko-Network/roko-edge-tools.git
cd roko-edge-tools
TIME_REGION=americas ./bin/roko-guided-install --time-stack chrony --dry-run
TIME_REGION=americas ./bin/roko-guided-install --time-stack chrony
```

Choose `global`, `americas`, `europe`, `asia`, `oceania`, or `africa`. The
profile includes the public ROKO NTP node as one source and requires two
selectable sources.

After installation:

```bash
./bin/roko-time-health
./bin/roko-edge-doctor
./bin/roko-rpc-health --rpc http://127.0.0.1:9944
```

Consumer routers, sleep states, Wi-Fi roaming, VMs without stable clocks, and
overloaded storage can increase jitter. Recheck after reboots and network
changes. Do not serve public NTP from a home node; if serving a private LAN,
restrict `allow` to the exact private subnet and disable the remote command
port.

---

Pagenbar: [← Choose sources](choose-sources.md) · [Index](README.md) · [Next: Professional design →](professional.md)
