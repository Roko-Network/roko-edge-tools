---
id: roko-time-authority.timebeat-ptp2
title: Timebeat and PTP Squared integration
summary: Licensed package handling, configuration boundaries, and coexistence with ROKO.
audience: [professional, agent]
tasks: [install, integrate, verify]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Adding licensed Timebeat software or an operator PTP Squared authority.
previous: professional.md
next: security-network.md
---

# Timebeat and PTP Squared integration

The public installer verifies the pinned Timebeat 2.3.5 package checksum. The
operator supplies a per-node licence and reviewed configuration using public or
self-operated authorities. Public documentation never contains private ROKO
timing topology.

```bash
./bin/roko-guided-install --time-stack timebeat --dry-run
./bin/roko-guided-install --time-stack timebeat
```

Before approval, confirm:

- package architecture and checksum match;
- licence is a private local file with restrictive permissions;
- configuration contains the intended PTP Squared section;
- authority ownership, source count, interfaces, seats, and clock-steering
  behavior match the reviewed design;
- Chrony and Timebeat do not compete to steer the system clock;
- required PTP Squared and ROKO P2P egress is allowed, without exposing RPC.

ROKO PTP² (`/roko/timesync/1`) and Timebeat PTP Squared are distinct protocols.
Installing one does not configure, enroll, or prove the other. Service-active
is not an acceptance test; verify live sources, offsets, root distance,
convergence, logs, and behavior during source loss.

Never paste licence contents or proprietary configuration into an agent prompt.
Provide local paths only.

---

Pagenbar: [← Professional design](professional.md) · [Index](README.md) · [Next: Security/network →](security-network.md)
