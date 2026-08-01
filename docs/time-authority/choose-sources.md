---
id: roko-time-authority.source-selection
title: Choose and qualify time sources
summary: Regional source directory and an evidence-based selection procedure.
audience: [hobbyist, professional, agent]
tasks: [select, probe, qualify]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Before writing Chrony or Timebeat configuration.
previous: concepts.md
next: hobbyist.md
---

# Choose and qualify time sources

Use at least two selectable sources. One can be ROKO's public Stratum 2 node;
pair it with a geographically close Stratum 1 or 2 authority.

## Source directory

| Region | Traceable source | Diversity source |
| --- | --- | --- |
| Americas | `time-a-g.nist.gov` or `time-d-b.nist.gov` | `north-america.pool.ntp.org` |
| Europe | `ptbtime1.ptb.de` or `ptbtime4.ptb.de` | `europe.pool.ntp.org` |
| Asia | `ntp.nict.jp` | `asia.pool.ntp.org` |
| Oceania | `ntp.nict.jp` when routing is suitable | `oceania.pool.ntp.org` |
| Africa | nearest measured NIST/PTB source | `africa.pool.ntp.org` |
| ROKO network | `ntp01.roko.network` (Stratum 2 at last review) | Never use as the only source |

Official directories: [NIST](https://tf.nist.gov/tf-cgi/servers.cgi),
[PTB](https://www.ptb.de/cms/en/ptb/fachabteilungen/abt9/gruppe-95/ref-952/time-synchronization-of-computers-using-the-network-time-protocol-ntp.html),
[NICT](https://www.nict.go.jp/en/sts/ntp.html), and
[NTP Pool zones](https://www.ntppool.org/en/use.html). Pool membership and
stratum vary; inspect the servers actually selected.

## Qualify from the target network

```bash
ntpdate -q -u ntp01.roko.network
ntpdate -q -u time-a-g.nist.gov
```

Then run candidates under Chrony for at least 30 minutes and inspect:

```bash
chronyc tracking
chronyc sources -v
chronyc sourcestats -v
```

Reject a candidate when it is persistently unreachable, falseticker (`x`), too
variable (`~`), has abnormal leap state, excessive root distance, or a route
that is consistently much worse than alternatives. Do not hard-code an IP when
the authority documents a managed hostname.

## Example

```conf
server ntp01.roko.network iburst minpoll 6 maxpoll 10
server time-a-g.nist.gov iburst minpoll 6 maxpoll 10
pool north-america.pool.ntp.org iburst maxsources 2
minsources 2
```

---

Pagenbar: [← Concepts](concepts.md) · [Index](README.md) · [Next: Hobbyist setup →](hobbyist.md)
