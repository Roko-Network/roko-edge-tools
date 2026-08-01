---
id: roko-time-authority.hardware-acceptance
title: Hardware clock acceptance and lifecycle
summary: Mainnet GNSS gates, TOD/PPS tests, holdover exercises, monitoring, maintenance, and evidence.
audience: [professional, agent]
tasks: [verify, qualify, maintain]
status: draft-mainnet-policy
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Qualifying hardware before mainnet enrollment or after maintenance.
previous: hardware-deployment.md
next: timebeat-ptp2.md
---

# Hardware clock acceptance and lifecycle

Hardware is accepted only by observed behavior. Presence and service-active
state are insufficient.

## Mainnet gates

- GNSS is active with sustained satellites used in the timing solution.
- Position and UTC TOD are valid; antenna and interference alarms are clear.
- PPS is live, stable, and linked to the same GNSS/TOD chain.
- PHC, oscillator, servo, and system-clock states are locked/normal.
- Independent UTC checks prove the correct whole second and acceptable offset.
- At least two external bootstrap/cross-check sources remain selectable.
- GNSS loss enters declared holdover and alarms without claiming GNSS lock.
- GNSS recovery is observable and causes no unsafe time step.
- Timebeat/PTP Squared and ROKO evidence meet the reviewed profile.
- The node remains non-authoring until separate mainnet enrollment.

After oscillator warm-up, perform controlled GNSS loss and recovery tests.
Measure holdover error versus time under normal temperature/load, alarm latency,
client behavior, and recovery. Simulate or isolate at an approved service
boundary; never disconnect rooftop or energized antenna systems unsafely.

Test reboot, cold start, service restart, source/network/monitoring loss,
leap-state handling, rollback, and replacement hardware. Requalify after
antenna, cable, firmware, kernel, driver, oscillator, BIOS, Timebeat, or topology
changes.

Retain value-free evidence: revisions, GNSS constellation/satellite counts,
TOD validity, PPS/PHC mapping, servo state, offset, root distance, holdover
curve, alarms, checksums, configuration revision, observation period, approver,
and rollback result. Alert continuously on GNSS/PPS/TOD loss, antenna faults,
spoof/jam indicators, oscillator unlock, holdover age, offset, source
disagreement, temperature/power, ROKO convergence, quality, and finality.

Active GNSS is an ongoing mainnet condition, not a one-time installation check.

---

Pagenbar: [← Hardware deployment](hardware-deployment.md) · [Index](README.md) · [Next: Timebeat/PTP² →](timebeat-ptp2.md)
