---
id: roko-time-authority.orientation
title: ROKO time authority deployment
summary: Entry point and deterministic route map for establishing time before joining ROKO.
audience: [hobbyist, professional, agent]
tasks: [route, scope, install]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Start here for every ROKO time or node deployment.
next: concepts.md
---

# ROKO time authority deployment

Establish trustworthy host time before joining ROKO. Every deployment needs at
least two selectable sources. One may be the public ROKO Stratum 2 service at
`ntp01.roko.network`; the other should be a nearby Stratum 1 or 2 source in a
different administrative and network failure domain.

This docset intentionally contains no private ROKO timing topology.

## Choose your path

| Goal | Read in order |
| --- | --- |
| Hobbyist node | [Concepts](concepts.md) → [Choose sources](choose-sources.md) → [Hobbyist setup](hobbyist.md) → [Verification](verification.md) |
| Professional node or validator candidate | [Concepts](concepts.md) → [Choose sources](choose-sources.md) → [Professional design](professional.md) → [Security](security-network.md) → [Verification](verification.md) |
| Mainnet physical clock | Professional path → [Hardware selection](mainnet-hardware.md) → [GNSS site installation](gnss-site-installation.md) → [Hardware deployment](hardware-deployment.md) → [Hardware acceptance](hardware-acceptance.md) |
| Licensed Timebeat/PTP Squared | Professional path, then [Timebeat and PTP Squared](timebeat-ptp2.md) |
| Diagnose a deployment | [Verification](verification.md) → [Troubleshooting](troubleshooting.md) |
| Agent-assisted deployment | [Agent contract](agent-contract.md), which routes back through the applicable pages |

## Non-negotiable acceptance conditions

- Chrony reports `Leap status: Normal`.
- At least two sources are selectable (`*` or `+` in `chronyc sources -v`).
- The ROKO public source is not the only selected authority.
- The host is stable before the ROKO node starts.
- A validator candidate remains non-authoring until separate enrollment.
- Every mainnet validator has directly connected, active GNSS; network-only synchronization and oscillator-only holdover do not satisfy enrollment.
- Secrets, licences, private keys, and proprietary configuration contents never
  enter prompts, logs, reports, or Git.

The machine-readable route graph is [`docset.yaml`](docset.yaml).

---

Pagenbar: **Start** · [Index](README.md) · [Next: Concepts →](concepts.md)
