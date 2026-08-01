---
id: roko-time-authority.verification
title: Verification, monitoring, and acceptance
summary: Commands, thresholds, evidence, and ongoing health checks.
audience: [hobbyist, professional, agent]
tasks: [verify, monitor, accept]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: After configuration, before joining, and during routine operations.
previous: security-network.md
next: troubleshooting.md
---

# Verification, monitoring, and acceptance

Run:

```bash
chronyc tracking
chronyc sources -v
chronyc sourcestats -v
timedatectl status
./bin/roko-time-health
./bin/roko-edge-doctor
```

Accept clock bootstrap only when:

- leap status is normal;
- at least two sources are selectable (`*` or `+`);
- reach registers remain healthy across several polls;
- offset, root distance, frequency, and skew are stable for the deployment;
- source disagreement is understood and no falseticker is selected;
- the ROKO public source is not the only authority.

For a ROKO node, additionally require the expected genesis, peers greater than
zero, `isSyncing: false`, stable identity, advancing finality, and the intended
non-authoring role. Validator candidates require temporal convergence and at
least two mapped authority peers before separate activation review.

Professional monitoring should alert on unsynchronized/leap-alarm state,
selected-source stratum changes, source count below two, abnormal root distance,
offset or frequency excursions, service restarts, source disagreement, mesh
quality degradation, loss of finality, and configuration drift.

Record values and timestamps in operational telemetry, but keep secrets and
private configuration out of readiness reports.

---

Pagenbar: [← Security/network](security-network.md) · [Index](README.md) · [Next: Troubleshooting →](troubleshooting.md)
