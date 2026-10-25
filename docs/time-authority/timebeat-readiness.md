---
id: roko-time-authority.timebeat-readiness
title: Read-only Timebeat readiness reports
summary: Bounded local inventory, explicit unknown runtime evidence, and prerequisites for a shared-feed trial.
audience: [professional, agent, operator]
tasks: [diagnose, verify, qualify]
status: experimental
version: 0.1.0
last_reviewed: 2026-10-24
read_when: Assessing installed Timebeat, a shared PTP Squared mesh, or a managed timing feed.
previous: timebeat-ptp2.md
next: security-network.md
---

# Read-only Timebeat readiness reports

Use `bin/roko-timebeat-readiness` for bounded local facts and unresolved
qualification gates. It preserves the distinction between an operator's
configuration summary and actual runtime behavior. The Timebeat runtime CLI
adapter is **not yet qualified**: a report cannot authorize an observation trial
or a clock-source cutover.

The tool runs no installer, restart, clock adjustment, firewall change or remote
probe. It reads no Timebeat configuration, licence, environment or process
arguments. Local commands use fixed executable paths and read-only arguments,
with a 20-second total budget, two seconds per command and a 16 KiB output cap.
Unrecognized output, missing tools and permissions remain unknown. No CLI
password, Vault token or credential option exists.

## Run one bounded report

From this repository checkout:

```bash
./bin/roko-timebeat-readiness --help
./bin/roko-timebeat-readiness
```

JSON is written to stdout. Exit `3` means qualification is unknown; exit `2`
means a known diagnostic failure or invalid invocation. This initial tool has
**no ready/success exit**. A generated report or active service is insufficient
evidence of working timing.

Use only an interface, local listener port and recovery timer already selected
in your reviewed host/connection plan. Omit selectors when unknown; do not guess
ports or copy another installation's interface/device names. The tool queries
local socket state rather than opening a connection to the requested port.

```bash
./bin/roko-timebeat-readiness \
  --interface "$REVIEWED_INTERFACE" \
  --listener-port "$APPROVED_LOCAL_PORT" \
  --recovery-timer "$REVIEWED_RECOVERY_TIMER"
```

Interface and timer names, addresses, raw dependency names and command output
are omitted from JSON. Timer labels follow the supplied order. No selected
timers does not mean no recovery automation exists. Listener presence does not
prove process ownership, peer connection, an occupied seat or usable timing.
An active service with none of the explicitly requested listeners is reported
as a diagnostic failure; its cause remains unestablished.

This is a one-shot check, not a new polling service. Reuse existing minutely
reports; retain varied report times, at least 30 seconds between reports per
host and no catch-up bursts. PTP/servo exchange rates are separate reviewed
settings; this tool does not change either schedule.

## What the local facts establish

| Evidence | Reported fact | Qualification still needed |
| --- | --- | --- |
| Package / disk binary / `/proc` running executable | Separate version tokens and a mismatch check; deleted running-image indication where accessible | Exact-version provider support and runtime CLI semantics; packaging/edition differences are not silently treated as identical |
| Selected service properties | Presence, activity and separate `After`/`Requires`/`Wants` relations to a small fixed set of clock/startup units | Actual clock-adjustment ownership and executable readiness-gate logic |
| Selected recovery timers | Presence/activity of the requested units | Complete automation inventory and ownership assumptions |
| Chrony tracking | Reported synchronization, stratum, RMS offset, root delay/dispersion and skew | Independent UTC error, source ancestry and long-window accuracy |
| Visible PHC/PPS devices | Counts in the current device namespace | Device mapping, access, GNSS/PPS lock, servo behavior and UTC relationship |
| `ethtool -T` | Hardware/software capabilities and reported PHC index | Actual runtime timestamp mode and clock domain |
| Requested local socket ports | Listener counts | Discovery, connected peers, occupied seats and selected usable timing sources remain separate, unverified quantities |

`verified` means the specific local observation was parsed, not that Timebeat,
UTC accuracy or a shared feed is qualified. Missing values stay null. Genuine
zero measurements remain zero. No source identifier, licence validity or
hardware qualification is inferred from process activity.

## Existing collector / Vault interface

The existing authorized collector and Vault lifecycle remain responsible for
any restricted Timebeat CLI access, scoped permissions, renewal/expiry and
recovery. This public tool adds no credential store, SSH client, password
fallback or arbitrary command hook. Do not pass authentication values through
arguments, environment, reports or Git.

A collector can hand off a **dedicated, sanitized ROKO JSON summary** using the
following options. They are ROKO handoff schemas, not a claimed vendor CLI JSON
format. Never point them at a Timebeat configuration, licence, identity or
keystore file. Inputs must be regular non-symlink files no larger than 64 KiB.

```bash
./bin/roko-timebeat-readiness --offline \
  --configuration-summary ./timebeat-config-summary.json \
  --runtime-evidence ./timebeat-runtime-evidence.json
```

`--offline` skips every host command and device probe. It cannot verify a
running executable or authenticate the supplied evidence. The only accepted
configuration fields are:

- `schema: "roko.timebeat-config-summary.v1"`, optional `configuration_sha256`;
- `ptpsquared_enabled`, `adjust_clock`, `interface_supplied` booleans;
- `clock_domain` (`system`, `phc`, `unknown`) and `adjustment_owner` (`chrony`,
  `timebeat`, `ptp4l`, `phc2sys`, `other`, `unknown`);
- `source_kind` (`vendor_mesh`, `managed_feed`, `operator_mesh`, `unknown`);
- `domain` (0–255), `bootstrap_count`, `offer_seats`, `fill_seats`,
  `concurrent_sources`, `report_interval_seconds`, and signed 8-bit
  `ptp_log_sync_interval`.

Configuration claims are never promoted to verified runtime flags. In
particular, `adjust_clock: false` or zero offered seats does not prove that all
clock domains and downstream distribution are inert in the deployed version.

The runtime schema is `roko.timebeat-runtime-evidence.v1`, with UTC `captured_at`
ending in `Z` and `timebeat_version`. Its allow-listed measurements are
`discovered_peers`, `connected_peers`, `occupied_seats`,
`selected_usable_sources`, `utc_sample_age_seconds`, `utc_uncertainty_ns`,
`servo_residual_ns`, `clock_domain`, `timestamp_mode` (`hardware`, `software`,
`unknown`), `adjustment_observed` and `protocol_exchange_hz`. Counts and
uncertainty are unsigned 32-bit integers; servo residual is signed 64-bit.
Unknown or invalid fields are dropped or null, and arbitrary strings are not
exported.

Provided runtime values remain explicitly **unverified**, even when schema,
version and wrapper age match. An input's `approved` or `qualified` flag cannot
change that. Wrapper age above 150 seconds is stale for this minutely handoff;
a future timestamp beyond five seconds fails the time check. This check uses
the local system clock and is not an independent UTC certification or a
universal freshness threshold for NTP/PTP source samples.

## Version and decision status — 2026-10-24

| Version / interface | Current qualification |
| --- | --- |
| Timebeat 2.3.5 | Package/disk/running version-command format observed in the dated investigation; this tool's local parsing is tested with synthetic fixtures. Runtime seats, selected sources, no-steering behavior and authenticated CLI adapter are not qualified. |
| 2.3.2-enterprise | Historical reference only; current installation, licence and runtime interfaces require fresh qualification. |
| Other versions / unsupported output | Retain observed version when recognized, otherwise unknown. No supported shared-feed/profile compatibility is claimed. |

PTP Squared federation, a managed Timing Feed and an operator's own mesh are
different options. As of this review, shared-mesh availability, admission and a
provider-supported connection contract remain unverified; no retirement or
supplier-availability claim is made. Licensing and network-program terms must
be independently confirmed; a running agent or this report establishes no
entitlement, redistribution permission or payout.

The delivery dependencies are public and explicit:

1. [Access and supported connection details (#53)](https://github.com/Roko-Network/roko-edge-tools/issues/53).
2. [Diagnostics and exact-version runtime adapter (#54)](https://github.com/Roko-Network/roko-edge-tools/issues/54): this tool delivers local inventory and safe unknown-state reporting; CLI transport/semantics qualification remains open.
3. [Isolated non-authoring observation trial (#55)](https://github.com/Roko-Network/roko-edge-tools/issues/55): requires access, qualified diagnostics, verified no-steering semantics and rollback, then at least 24 hours of evidence. No such completed trial is claimed here.
4. [Qualified guidance and rollout decision (#56)](https://github.com/Roko-Network/roko-edge-tools/issues/56): this page prepares diagnostics guidance. The supported profile matrix and production go/no-go still depend on the trial.

Keep the existing clock regime while these gates are unresolved. A later
one-host cutover requires exactly one writer per clock domain, reviewed recovery
and startup automation, independently qualified fallback, numerical
error/holdover acceptance and tested loss/recovery/rollback. A failed or
inconclusive trial leaves that regime intact.

For conditional repairs use the [clock-alignment checklist](validator-timing.md#bring-the-clock-into-alignment).
Preserve readiness/admission gates and separate consensus participation from
clock quality. [Local node wallet enrollment](../validator-node-wallet.md)
remains the primary enrollment procedure; timing diagnostics do not rotate keys
or re-enroll a validator. Review sanitized reports before sharing; do not send
full logs, environment/configuration dumps, private keys or licence contents.

---

Pagenbar: [← Timebeat integration](timebeat-ptp2.md) · [Index](README.md) · [Next: Security/network →](security-network.md)
