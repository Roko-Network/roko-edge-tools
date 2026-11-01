---
id: roko-time-authority.stratum1-bootstrap
title: Nearest stratum-1 sources and scheduled bootstrap
summary: Find the nearest healthy stratum-1 NTP servers, add them to Chrony, and schedule a recurring refresh-and-verify check.
audience: [hobbyist, professional, agent]
tasks: [select, configure, schedule, verify]
status: stable
version: 1.0.0
last_reviewed: 2026-10-31
read_when: After the clock passes verification, to keep it tied to nearby stratum-1 UTC and be alerted when it drifts.
previous: verification.md
next: validator-timing.md
---

# Nearest stratum-1 sources and scheduled bootstrap

Three tools keep a node's clock tied to nearby stratum-1 UTC:

| Tool | Does | Changes the host |
| --- | --- | --- |
| `bin/roko-stratum1-select` | Measures public stratum-1 servers from this host and picks the nearest healthy ones | Only with `--install`: writes one Chrony sources file and reloads sources |
| `bin/roko-stratum1-bootstrap` | Requests a Chrony measurement burst, waits for the 1 ms sync gate, verifies a fresh stratum-1 source agrees and the clock runs at local stratum 2 or better | No; it never steps the clock |
| `bin/roko-stratum1-schedule` | Runs the bootstrap check hourly with a systemd timer or cron | Only with `--execute` |

They work with Chrony as the single clock owner. None of them steps the clock,
restarts Chrony or the node, or removes your existing sources, so the
[two-source requirement](verification.md) still holds.

## 1. Find your nearest stratum-1 servers

```bash
./bin/roko-stratum1-select
```

The tool queries each catalog server four times, four seconds apart, from this
host. It keeps servers that answer as stratum 1 without a leap alarm and ranks
them by round-trip time. It selects the nearest one, plus the nearest one run by
a different operator for diversity. Expected output ends with a preview:

```text
server                       operator   stratum min RTT ms  status
time-a-g.nist.gov            NIST             1      18.06  SELECTED
ntp1.npl.co.uk               NPL              1      78.41  SELECTED
...
server time-a-g.nist.gov iburst prefer minpoll 6 maxpoll 10
server ntp1.npl.co.uk iburst minpoll 6 maxpoll 10
```

The catalog (`installer/stratum1-candidates.json`) covers North America,
Europe and Japan. Elsewhere, add the national time laboratory nearest you from
its official directory (see [Choose sources](choose-sources.md)):

```bash
./bin/roko-stratum1-select --candidate ntp.example-lab.org
./bin/roko-stratum1-select --only-candidates --candidate ntp.example-lab.org
```

The measured offset in `--json` output is indicative only; it includes network
path asymmetry. Selection uses round-trip time.

Exit codes: `0` selected, `2` invalid option, `3` no reachable stratum-1 server
(check outbound UDP 123), `4` install not possible as configured.

## 2. Add them to Chrony

```bash
sudo ./bin/roko-stratum1-select --install
```

This writes `roko-stratum1.sources` into the `sourcedir` declared in
`chrony.conf` (Debian and Ubuntu use `/etc/chrony/sources.d`), keeps any
previous copy as `.bak`, and runs `chronyc reload sources`. If your
`chrony.conf` has no `sourcedir`, the tool changes nothing, prints the lines,
and exits `4`; add them to `chrony.conf` yourself and restart Chrony during a
maintenance window.

Then watch `chronyc sources -v` over several polls until a selected stratum-1
server shows `*` and reach stays healthy. Re-run selection after moving a host
or changing networks.

## 3. Check once, then schedule it

```bash
sudo -u _chrony ./bin/roko-stratum1-bootstrap   # Fedora/RHEL: sudo -u chrony
```

Expected: `roko-stratum1-bootstrap: OK 1/2 stratum-1 source(s) fresh within 0.005s; disciplined by ... at stratum 2`.
A `FAIL` line names the failed gate and exits non-zero.

Preview the schedule, then apply it:

```bash
./bin/roko-stratum1-schedule                 # dry run: prints the plan
sudo ./bin/roko-stratum1-schedule --execute  # systemd timer, hourly
sudo ./bin/roko-stratum1-schedule --cron --execute   # hosts without systemd
```

The check is copied to `/usr/local/libexec/roko-stratum1-bootstrap` and runs as
the Chrony user. Each host gets a stable random minute so public servers are
not queried at the same moment by every node. Results go to the journal:

```bash
systemctl list-timers roko-stratum1-bootstrap.timer
journalctl -u roko-stratum1-bootstrap --since today     # systemd
journalctl -t roko-stratum1-bootstrap --since today     # cron
```

A failed run leaves `roko-stratum1-bootstrap.service` in `systemctl --failed`;
alert on that. Remove everything with `sudo ./bin/roko-stratum1-schedule --remove --execute`.
The scheduler refuses to overwrite a `roko-stratum1-bootstrap` unit it did not
install.

Thresholds are environment variables documented at the top of
`bin/roko-stratum1-bootstrap` (defaults: 5 ms offset, 180 s sample age, one
source, local stratum 2). Keep the defaults unless your operator approves a
change; do not loosen them to make a failing check pass.

## When the check fails

| Message | Meaning | Next step |
| --- | --- | --- |
| `chronyc burst was refused` | Not running as root or the Chrony user, or chronyd stopped | Fix the unit user or start chronyd |
| `did not reach its sync gate` | Offset above 1 ms after 60 s | Follow [Validator timing](validator-timing.md#bring-the-clock-into-alignment) |
| `no stratum-1 source is configured` | Step 2 not done | `sudo ./bin/roko-stratum1-select --install` |
| `0/N stratum-1 source(s) fresh` | Selected servers unreachable or disagree | Re-run selection; check outbound UDP 123 |
| `disciplined by ... at stratum 3` | Chrony prefers a farther source | Confirm the `prefer` server is reachable, then re-run selection |

## Agent procedure

An agent asked to set up nearest stratum-1 discipline must follow the
[agent contract](agent-contract.md) and:

1. Run `./bin/roko-node-snapshot --no-rpc --quiet --json` if available, or
   `chronyc tracking`, to record the starting state. Stop if leap status is not
   normal or Chrony is not the clock owner.
2. Run `./bin/roko-stratum1-select --json` and show the operator the ranked
   table and the proposed sources file.
3. Wait for explicit approval, then run `sudo ./bin/roko-stratum1-select --install`.
4. Run the one-off check as the Chrony user and report its full output line.
5. Run `./bin/roko-stratum1-schedule` (dry run), show the plan, wait for
   approval, then add `--execute`.
6. Report: selected hosts and RTTs, sources file path, first check result,
   timer or cron schedule, and any failed gate.

Never edit `chrony.conf` directly, remove existing sources, step the clock,
restart Chrony or the node, change thresholds, or install the schedule on a
host whose existing `roko-stratum1-bootstrap` unit belongs to another manager.

---

Pagenbar: [← Verification](verification.md) · [Index](README.md) · [Next: Validator timing →](validator-timing.md)
