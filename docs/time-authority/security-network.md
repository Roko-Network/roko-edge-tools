---
id: roko-time-authority.security-network
title: Security and network exposure
summary: Firewall, authentication, least privilege, serving policy, and secret handling.
audience: [hobbyist, professional, agent]
tasks: [harden, expose, audit]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Before opening ports, serving clients, or handling licences and keys.
previous: timebeat-ptp2.md
next: verification.md
---

# Security and network exposure

## Default exposure

- NTP client: outbound UDP/123 and replies.
- NTS client: outbound TCP/4460 plus UDP/123 when supported.
- ROKO P2P: the published node P2P port required by the selected role.
- RPC and metrics: loopback or a protected management network only.
- Chrony command port: disabled remotely (`cmdport 0`) unless a separately
  authenticated management design requires it.

Do not open IEEE 1588 UDP/319 or UDP/320 for ROKO PTP²; ROKO's protocol is
carried over libp2p. Timebeat requirements depend on the reviewed vendor design.

## Serving NTP

Hobbyists should not expose public NTP. For a private LAN, use an exact `allow`
CIDR, bind only the intended address, rate-limit clients, and monitor
amplification risk. Professional public service additionally requires abuse
handling, redundant upstreams, capacity planning, DDoS controls, and external
probes.

## Secrets and supply chain

Verify packages and manifests before execution. Licences, node keys, session
keys, signing keys, and credentials must be local files or protected secret
store material—not argv, environment dumps, reports, or Git. Keep a package
inventory, source URLs, checksums, configuration revision, and approval record.

---

Pagenbar: [← Timebeat/PTP²](timebeat-ptp2.md) · [Index](README.md) · [Next: Verification →](verification.md)
