---
id: roko-time-authority.validator-timing
title: Validator timing and mesh quality
summary: Clock alignment decisions and read-only checks for UTC discipline, mesh agreement, and explorer history.
audience: [hobbyist, professional, agent]
tasks: [diagnose, verify, monitor]
status: stable
version: 1.1.0
last_reviewed: 2026-10-24
read_when: A validator or observer has falling quality, good Chrony readings, or an unexpected chart.
previous: verification.md
next: troubleshooting.md
---

# Validator timing and mesh quality

Check the host clock and the node's observations separately. A healthy selected
clock source and a lower mesh score can coexist. Preserve a short, timestamped
window before changing anything; a restart can reset the estimator and make the
score look better without establishing better UTC accuracy.

These details describe the native node build `fba4e76cfeb` with runtime spec
`290`, investigated on 2026-10-23. Record your actual node version and settings;
a runtime spec number alone does not identify the native estimator behavior.

## Bring the clock into alignment

1. **Check UTC discipline first.** Use the [read-only checks below](#bounded-read-only-checks).
   Confirm normal leap state, the intended selected reference, additional
   selectable sources and healthy reach across normal polls. Compare with an
   independent UTC reference already approved for this host. A small offset to
   one selected source or a good mesh score alone does not qualify UTC accuracy.
2. **Confirm the clock and its owner.** Establish whether node timestamps use
   the system clock or an explicitly configured PHC. Keep one approved clock
   adjuster per clock domain; software being installed does not establish
   ownership. Resolve unclear or conflicting adjustment ownership with the host
   operator before making a correction.
3. **Repair a demonstrated source fault under the existing maintenance plan.**
   If the intended source is missing or unreachable, restore its approved
   configuration or connectivity using the host runbook, then check selection
   and reach again. If a configured PHC has the wrong device mapping or an
   unlocked servo, follow the approved host/vendor procedure for that device
   and verify its relationship to UTC. Healthy system-clock Chrony readings do
   not establish that a separate PHC is disciplined. Do not assume a PHC exists
   or that `/dev/ptp0` is the intended device.
4. **Compare before and after.** Reuse existing minutely observations wherever
   available. Where no equivalent reports exist, use a bounded manual window
   such as five samples, at most once per minute at varied times and at least
   30 seconds apart; skip missed samples without catch-up. Do not increase or
   duplicate the configured reporting schedule. Compare UTC/source uncertainty
   and the same observer's mesh spread, reputation and sample ages. Re-run the
   [acceptance gate](verification.md) after a qualified repair.
5. **Keep healthy discipline intact when mesh disagreement persists.** Inspect
   peer freshness, accepted sample counts, path changes and software queue/load
   evidence. Escalate a [sanitized support packet](#share-a-sanitized-support-packet)
   when those observations do not explain the difference. Do not copy a mesh
   consensus offset into the host clock, raise thresholds, restart services or
   install hardware simply to make scores agree.

This flow selects a conditional repair, not a universal clock-setting command.
Retain failed readiness, admission and source-health gates until the relevant
fault is resolved and acceptance is demonstrated.

### Check participation separately

**Disabled** is finalized consensus participation status, not a clock
measurement. Improving clock discipline does not automatically clear it. Use
only authorized readiness/status checks for the intended validator role,
active-session/local-key match and offchain-worker-enabled booleans; mark
unavailable checks unknown. Ask the authorized key custodian for a status
confirmation rather than reading private key files. Do not re-enroll, rotate
keys, force an era/session or bypass readiness as a clock-alignment shortcut.

## Read the right metric

| Measurement | What it establishes | What it does not establish |
| --- | --- | --- |
| Chrony tracking and selected sources | The host's reported discipline, reference, uncertainty, frequency and synchronization state | Independent proof of absolute UTC accuracy or the node's chosen timestamp device |
| Legacy mesh `timeQuality` | Agreement among this observer's authority-mapped peer offset estimates and their statistical reputations | A percentage of correct UTC timestamps or a network-wide accuracy measurement |
| Mesh `Converged` | Configured source/sample requirements and peer spread are satisfied | A score near 100%, enrollment success, or accepted block authorship |
| Independent RPC history | Historical scores observed at the named RPC source | An average of all validators, or this operator's own node unless the source identity is verified |
| Managed-validator observations | The stated managed subset, with explicit eligibility and coverage | Measurements of missing or unobserved external validators |

`timeQuality` uses fixed units: `0..10000` displays as `0..100%`. A recorded
zero is valid; an unavailable measurement must remain unavailable.

The explorer's **Independent RPC** history currently shows the **minimum
successful score within each five-minute interval**. This is a worst observed
sample in that interval, not its mean. Missing readings and partial sampling
coverage are separate from the score; compare the same source and interval
before comparing screenshots. **Previous explorer** is a separate archived
series. Managed-validator minute summaries are another source and must not be
blended into the RPC series.

## Why a disciplined clock can have a falling mesh score

In the legacy model, for active authority-mapped peers with positive reputation:

```text
quality = source factor × spread factor × mean peer reputation
source factor = min(peer count / configured minimum sources, 1)
spread factor = max(1 - weighted offset spread / convergence threshold, 0)
```

The spread is a reputation-weighted standard deviation of estimated peer
offsets. For example, a spread factor of 75% and mean reputation of 80% gives
60% quality, while still potentially being `Converged`. The reported number is
not a direct conversion of the local clock's root distance.

Peer offsets use software timestamps in a four-timestamp exchange. Directional
network delay, application queues and load can affect them even when both host
clocks are disciplined. Accepted samples feed a moving average; statistical
reputation compares recent offset distributions. A changing path, peer
population, sample acceptance rate or those distributions can therefore produce
a gradual change. There is no explicit uptime-based decay in this build's
legacy quality formula. A common clock offset applied equally to every peer
would cancel in the spread; the chart alone cannot identify a faulty clock or
operator.

The deployed settings matter: the lucky-packet threshold also sets the regular
reputation agreement tolerance in this build. Raising thresholds, removing peers
or rescaling readings merely to improve the graph does not establish accuracy.
A diagnostic stale flag also does not, by itself, remove an old peer estimate
from this build's quality calculation.

## Verify the actual source and clock domain

A selected NIST Stratum 1 source can be the intended bootstrap source while
local GNSS is being prepared. Stratum describes reference hierarchy, not a
precision guarantee at your host. Internet path delay and asymmetry still
limit delivered accuracy. NIST explains that the user's observed accuracy is
largely determined by network stability and reciprocity in its
[Internet Time Service description](https://www.nist.gov/pml/time-and-frequency-division/time-distribution/internet-time-service-its).
Do not turn a Stratum 1 label into a nanosecond accuracy claim. This bootstrap
state does not satisfy the separate [mainnet GNSS acceptance requirements](hardware-acceptance.md).

For the investigated build:

- Probe timestamps use `CLOCK_REALTIME` by default, read at each timestamp.
  They are not generated by a startup-anchored raw monotonic clock.
- An explicit `--timesync-phc-path` selects a hardware clock instead. A healthy
  Chrony result for the system clock does not automatically qualify that PHC.
  Check the actual device, its discipline and its relationship to UTC using the
  hardware operator's approved read-only procedure; do not assume `/dev/ptp0`
  is the intended device.
- The optional anchor model is a different scoring model. It requires qualified
  source capability and health checks; merely installing PTP software does not
  enable it or prove direct UTC precision. Do not toggle it to improve a score.

Identify the one approved clock-adjustment owner for each clock domain. For
example, Timebeat presence does not mean it should also adjust a system clock
owned by Chrony. Inspect the reviewed settings locally; do not change adjustment
ownership, PHC mappings, source preference or flags as a diagnostic shortcut.

## Bounded read-only checks

On the host that owns the clock, run the commands available on that system:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
timedatectl status --no-pager
chronyc tracking
chronyc -n sources -v
chronyc -n sourcestats -v
```

Look for `Leap status: Normal`, the intended selected source (`*`), additional
selectable sources (`+`), reach history, and stable offset, root delay,
root dispersion, frequency and skew over several normal polls. A small offset
to the selected source alone is insufficient. If the tools are unavailable or
the discipline service runs elsewhere, mark those checks unavailable and ask
the host operator; do not install or reconfigure a clock service just to fill
in a report. See [Verification](verification.md) for the complete acceptance
gate.

From the node host, this existing tool uses read-only RPC methods over loopback:

```bash
./bin/roko-rpc-health --rpc http://127.0.0.1:9944 --json
```

For version and peer-level diagnostics, the following is a single bounded
read-only batch. Use the actual local RPC port; do not expose or forward RPC to
make the command work.

```bash
curl --fail --silent --show-error --max-time 8 \
  -H 'Content-Type: application/json' \
  --data '[{"jsonrpc":"2.0","id":1,"method":"system_version","params":[]},{"jsonrpc":"2.0","id":2,"method":"state_getRuntimeVersion","params":[]},{"jsonrpc":"2.0","id":3,"method":"temporal_getMeshState","params":[]}]' \
  http://127.0.0.1:9944
```

Check for RPC errors rather than treating absent fields as zero. Record version,
`timeQuality`, `convergenceState`, `offsetSpreadNs`, `convergenceThresholdNs`,
`producerAuthorityIndex` and each pairwise offset's reputation, sample count
and sample age. A null producer index means the observer is not currently
mapped as an authority; it does not identify a particular validator. The
transport peer count can exceed the authority-mapped scoring population.

Repeat a small number of times over normal polls, retaining UTC timestamps and
the same source identity. Compare spread and reputation separately. Record
reviewed nonsecret values for timestamp source, anchor model, convergence
threshold, lucky-packet threshold and probe interval. Do not dump complete
process arguments, environment variables or service configuration into a report.

## Share a sanitized support packet

Create a local note containing only:

- UTC start/end, node version/runtime spec, source identity and observed role;
- selected reference, leap state, reach, root delay/dispersion, offset, frequency
  and skew from the bounded window; include source root distance when reported,
  or retain the reported root delay and dispersion without inventing a value;
- the allow-listed mesh fields above, RPC error names, and whether samples are
  missing or stale;
- intended clock domain and adjustment owner, plus sanitized PHC/source-health
  warnings if present;
- explorer source, interval and whether the displayed value is a minimum or
  mean; any already recorded restart or configuration-change timestamps.

Review before sharing. Remove private addresses/hostnames where required,
credentials, tokens, licence contents, wallet material, recovery phrases,
keystores, session keys and complete configuration or environment dumps. The
existing support-report redaction is not a guarantee that arbitrary added data
is safe. Do not upload automatically or send wallet/enrollment files as timing
evidence.

Keep existing readiness, admission and source-health gates in force. A failed
gate requires assessment; never bypass it or force authoring to improve a score.

Keep the current configuration while the evidence is assessed. Do not run
`makestep`, restart services, alter clock ownership, weaken timing thresholds,
rotate keys, re-enroll or submit transactions in response to a low score alone.
A necessary correction needs a reviewed cause, a change plan and a fresh
acceptance window. [Local node wallet enrollment](../validator-node-wallet.md)
remains a separate procedure; timing diagnosis does not change that primary
path.

---

Pagenbar: [← Verification](verification.md) · [Index](README.md) · [Next: Troubleshooting →](troubleshooting.md)
