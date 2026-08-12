# AIWG-guided ROKO node installer

The installer follows the AIWG `setup.aiwg.io/v1` SetupManifest contract.
Scripts remain the primary artifacts. The bundled runner collects every
parameter before the first change, displays the complete plan, requires
confirmation, executes the same ordered steps as the manifest, verifies the
result, and offers a bounded service-restart recovery when appropriate.

No AIWG installation is required on the target node. AIWG agents can inspect
and operate the canonical manifests; operators can run the self-contained
guided launcher immediately.

## Hand this install to an AI agent

Give the agent
[`AGENT-INSTALL.md`](AGENT-INSTALL.md). It is the public, model-neutral
execution contract for the installer. It requires the agent to collect every
choice first, inspect the selected manifest and scripts, run the dry-run, wait
for explicit approval, and prove the full readiness gate before reporting
success.

The contract also prevents an agent from exposing RPC, deleting chain data,
handling key material, enabling validator authoring, or treating an active
service as proof of readiness. AIWG is optional; the bundled launcher is the
compatible execution path for agents that do not have the AIWG CLI.

## Choose the connectivity layers

Every installed role connects to the live ROKO blockchain P2P network through
the published bootnode and runs ROKO's `/roko/timesync/1` protocol. The role
and clock-stack choices determine how the host participates beyond that
baseline:

| Selection | ROKO chain P2P | ROKO PTP² | Timebeat PTP² Mesh |
| --- | --- | --- | --- |
| `full`, `archive`, or `validator-candidate` + Chrony | connected | non-advertising node protocol | not selected |
| `observer` + Chrony | connected | authenticated observer advertisement | not selected |
| `full`, `archive`, or `validator-candidate` + Timebeat | connected | non-advertising node protocol | operator-configured licensed mesh |
| `observer` + Timebeat | connected | authenticated observer advertisement | operator-configured licensed mesh |

ROKO PTP² is a ROKO libp2p protocol, not IEEE 1588 traffic on UDP/319 or
UDP/320. Timebeat PTP² is a separate timing product and network. Selecting
`observer` does not enroll a validator, and selecting Timebeat does not enable
ROKO observer advertisement.

## Choose the clock stack

Chrony bootstrap/testing/edge installation:

```bash
./bin/roko-guided-install --time-stack chrony --dry-run
./bin/roko-guided-install --time-stack chrony
```

Official partner validator-timing installation:

Timebeat is ROKO Network's endorsed official timing partner. Validator
operators targeting eligibility for the maximum payout tier must run a
licensed Timebeat deployment and join the Timebeat PTP² Mesh. Eligibility also
depends on measured performance and current network program rules.

1. Download the stable package for the host architecture and request a
   per-node licence directly from
   [Timebeat software downloads](https://www.timebeat.app/downloads/software).
2. Sign in to the vendor guides and prepare a configuration for public or
   operator-owned time authorities using the vendor's
   [installation](https://timebeat.app/community/platform/install-timebeat),
   [initial configuration](https://timebeat.app/community/platform/initial-configuration),
   and [PTP² Mesh](https://timebeat.app/community/platform/ptpsquared-mesh-basics)
   guides.
3. Save the package, licence, and reviewed configuration as local files on the
   target host. The guided installer verifies the pinned 2.3.5 package
   checksum and installs the reviewed files without displaying their contents.
4. Run:

```bash
./bin/roko-guided-install --time-stack timebeat --dry-run
./bin/roko-guided-install --time-stack timebeat
```

The public installer does not expose or depend on ROKO's internal timing
topology. Establish a public or self-operated time authority before joining
the network, and use at least two independent sources. The installer keeps
licence contents out of logs, Git, environment files, and ROKO service units.

Chrony remains the system-clock owner during qualification, using two
independent NIST sources. Timebeat runs with `adjust_clock: false` and provides
licensed PTP² mesh participation and evidence. The installer rejects active
ntpd or ptp4l daemons.

Treat regional pool entries as discovery/diversity sources rather than a
guaranteed stratum. Inspect `chronyc sources -v` and require at least two
selectable sources before continuing.

## What the installer completes

- platform, architecture, runtime, and disk-capacity preflight;
- Chrony installation and synchronization, or operator-licensed Timebeat
  installation and service activation;
- checksum-verified ROKO native binary or immutable container image;
- testnet chain specification;
- hardened, non-authoring full/archive/observer service;
- interactive ROKO `ptp2` observer-key insertion when that role is selected;
- matching genesis, ROKO peers, ROKO time-mesh RPC, non-authoring role, full
  sync, stable peer identity, and advancing finalized-head verification; and
- a value-free readiness report.

Before any change, the launcher shows the resolved node name, role, runtime,
clock owner, timeout, report location, and ordered steps. Use `--dry-run` to
review this plan. For automated lab provisioning, supply all documented
environment values and use `--non-interactive`; no implicit defaults are used
for missing required values.

The `validator-candidate` role first stops at a fully synchronized
non-authoring peer, then offers an optional interactive beginner handoff. It
walks the operator to wallet setup, holder claim or other testnet funding,
locking 50 ROKO, the release-matched native bond handoff, and the remaining
local session-key and signed-enrollment checks. The live runtime does not
expose EVM staking precompile `0x0700`, so a successful transaction to that
empty address is not accepted as bond proof. Wallet secrets and signing stay
in the user's wallet.
The installer never treats a bond or `--validator` as activation:

- [Prepare a validator](https://docs.roko.network/pages/prepare-validator.html)
- [Validator key custody](https://docs.roko.network/pages/validator-key-custody.html)

ROKO's built-in PTP² observer mode and Timebeat's licensed PTP² Mesh are
separate layers. The former is authenticated ROKO libp2p observation; the
latter is the endorsed partner timing product that steers and distributes
precision time and satisfies the partner-mesh requirement for maximum-tier
validator eligibility. Running the ROKO observer does not replace that
requirement.

## Direct AIWG use

The manifests are ready for AIWG's agentic-installer capability:

```bash
aiwg setup-validate installer/setup.user.manifest.yaml --strict
aiwg setup-validate installer/setup.timebeat.manifest.yaml --strict
aiwg setup-run installer/setup.user.manifest.yaml --dry-run
```

Some current AIWG builds index the `setup-run` and `setup-validate` skills but
do not expose those top-level CLI commands. In that case, use
`bin/roko-guided-install`; it implements the same fixed script ordering and
safety gates without blocking the installation on the AIWG CLI version.

If a step fails, correct the reported condition and rerun the launcher. The
scripts are idempotent where practical and preserve previous Timebeat
configuration and licence files before replacement. Destructive resets are
intentionally not provided.
