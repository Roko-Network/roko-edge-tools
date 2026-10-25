---
id: roko-time-authority.troubleshooting
title: Troubleshooting and recovery
summary: Symptom-driven diagnosis for source, stratum, offset, service, and mesh failures.
audience: [hobbyist, professional, agent]
tasks: [diagnose, recover]
status: stable
version: 1.0.0
last_reviewed: 2026-10-23
read_when: A source is unusable, stratum is unexpected, quality falls, or startup fails.
previous: validator-timing.md
next: agent-contract.md
---

# Troubleshooting and recovery

| Symptom | Likely cause | Safe next check |
| --- | --- | --- |
| Stratum is one higher than expected | Normal NTP hop behavior | Check selected source in `chronyc tracking` |
| Public server unexpectedly serves Stratum 4 | It selected a Stratum 3 upstream | Inspect `Reference ID` and `chronyc sources -v` |
| `Stratum 0` / leap alarm | No selectable source or startup convergence | Check reachability, DNS, firewall, and logs; do not serve clients yet |
| Only one source selected | Other sources unreachable or rejected | `chronyc sources -v` and `sourcestats -v` |
| Source marked `x` | Falseticker/source disagreement | Investigate routes and independent reference; never force-select blindly |
| Large root distance | Network delay, upstream uncertainty, or extra hops | Choose a closer authority and inspect route/load |
| Timebeat active but no useful samples | Configuration, licence, egress, or authority issue | Inspect sanitized service logs and reviewed profile |
| ROKO mesh not converged or quality falls | Insufficient mapped peers, source health, changing paths or statistical agreement | Compare clock discipline, peer spread, reputation and sample ages using the [timing guide](validator-timing.md) |

Recovery order:

1. Preserve current evidence and configuration revision.
2. Separate host clock health from mesh agreement using the read-only checks.
3. If source health fails, have the operator review the intended sources and clock-adjustment owner.
4. Apply only the reviewed correction; a low score alone does not justify a clock step, service restart or role change.
5. Re-run the complete acceptance gate.
6. Change one node at a time and confirm network finality.

Never delete chain data, regenerate identity, weaken the two-source gate, or
activate authority as a time-recovery shortcut.

---

Pagenbar: [← Validator timing](validator-timing.md) · [Index](README.md) · [Next: Agent contract →](agent-contract.md)
