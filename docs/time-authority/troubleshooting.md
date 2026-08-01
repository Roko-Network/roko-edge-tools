---
id: roko-time-authority.troubleshooting
title: Troubleshooting and recovery
summary: Symptom-driven diagnosis for source, stratum, offset, service, and mesh failures.
audience: [hobbyist, professional, agent]
tasks: [diagnose, recover]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: A source is unusable, stratum is unexpected, quality falls, or startup fails.
previous: verification.md
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
| ROKO mesh not converged | Insufficient mapped peers or unstable host time | Fix host discipline first; then inspect ROKO peer metrics |

Recovery order:

1. Preserve current evidence and configuration revision.
2. Keep or return the ROKO node to non-authoring mode.
3. Restore at least two known-good public sources.
4. Restart only the affected clock service and wait for normal leap state.
5. Re-run the complete acceptance gate.
6. Change one node at a time and confirm network finality.

Never delete chain data, regenerate identity, weaken the two-source gate, or
activate authority as a time-recovery shortcut.

---

Pagenbar: [← Verification](verification.md) · [Index](README.md) · [Next: Agent contract →](agent-contract.md)
