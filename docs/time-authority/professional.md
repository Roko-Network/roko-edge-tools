---
id: roko-time-authority.professional
title: Professional and validator-candidate deployment
summary: Design, rollout, evidence, redundancy, and change-control requirements.
audience: [professional, agent]
tasks: [design, deploy, operate, audit]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Designing production, institutional, or validator-candidate timing.
previous: hobbyist.md
next: mainnet-hardware.md
---

# Professional and validator-candidate deployment

## Design before installation

Document reference lineage, expected stratum, AS paths, firewall state,
holdover behavior, clock hardware, virtualization, monitoring, owners, and
rollback. Separate clock authority, ROKO node, public RPC, and public NTP roles
unless the risk assessment explicitly accepts co-location.

Minimum design:

- two selectable upstream sources from different failure domains;
- `ntp01.roko.network` may be one, but never the only one;
- one daemon/policy owns system-clock steering;
- local RPC and Chrony command interfaces remain private;
- alerting covers source loss, leap state, offset, root distance, frequency,
  source disagreement, ROKO convergence, peer mapping, and finality;
- configuration and package checksums are recorded without secrets;
- rollback restores the previous known-good source set without deleting data.

## Controlled rollout

1. Capture pre-change tracking, sources, service status, and ROKO state.
2. Run the installer dry-run and peer review the resolved plan.
3. Bootstrap clock discipline before starting the node.
4. Observe source stability through normal route and load variation.
5. Start as a non-authoring peer and complete the readiness gate.
6. Rebootstrap or activate one node at a time; confirm finality before the next.
7. Retain a value-free deployment receipt and monitoring baseline.

For validator candidates, require two mapped ROKO temporal peers and converged
state in addition to Chrony acceptance. Enrollment, bonding, session-key
custody, and authority activation remain separate reviewed operations.

Mainnet additionally requires a physical hardware clock with directly
connected, active GNSS at every validator site. Continue through the hardware
selection, site, deployment, and acceptance pages before Timebeat integration.

## Higher-assurance options

Use NTS where both client and authority support it, dedicated GNSS/PTP hardware
with documented holdover, hardware timestamping, redundant network paths, and
independent out-of-band monitoring. Treat GNSS as an attack surface: antenna
placement, jamming/spoofing detection, and holdover performance need explicit
controls.

---

Pagenbar: [← Hobbyist setup](hobbyist.md) · [Index](README.md) · [Next: Mainnet hardware →](mainnet-hardware.md)
