---
id: roko-time-authority.concepts
title: Time concepts and trust boundaries
summary: Explains stratum, source selection, PTP, PTP Squared, and the ROKO temporal mesh.
audience: [hobbyist, professional, agent]
tasks: [learn, design]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Before selecting sources or deciding which daemon controls the clock.
previous: README.md
next: choose-sources.md
---

# Time concepts and trust boundaries

## Stratum is lineage, not a quality score

A Stratum 1 NTP server is directly attached to a reference clock. A server
synchronized to it normally serves clients as Stratum 2. Each NTP hop adds one.
Low stratum does not guarantee low latency, symmetric routing, availability, or
honest operation; measure those separately.

PTP or PTP Squared participation does not set the NTP stratum field. Chrony
advertises the lineage of the NTP source it selected.

## The layers

| Layer | Purpose | Typical owner |
| --- | --- | --- |
| Reference authority | Realizes or traces UTC | National lab, GNSS grandmaster, operator authority |
| Host discipline | Selects sources and steers the system clock | Chrony during bootstrap/qualification |
| Timebeat PTP Squared | Licensed precision-time measurement/distribution | Timebeat with reviewed operator configuration |
| ROKO temporal mesh | Measures authenticated peer time and convergence | ROKO node `/roko/timesync/1` protocol |
| Consensus | Produces and finalizes blocks | Enrolled validators |

Run one system-clock steering policy at a time. Observation daemons may coexist
only when they are explicitly configured not to steer the clock.

## Diversity means different failure domains

Two hostnames are not necessarily independent. Prefer differences in operator,
geography, autonomous system, reference technology, and transport. A practical
bootstrap combines `ntp01.roko.network` with a nearby national-laboratory
Stratum 1 service and optionally a regional pool for discovery.

---

Pagenbar: [← Orientation](README.md) · [Index](README.md) · [Next: Choose sources →](choose-sources.md)
