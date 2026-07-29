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
2. Sign in to the vendor guides, then prepare and review `timebeat.yml` using
   the vendor's
   [installation](https://timebeat.app/community/platform/install-timebeat),
   [initial configuration](https://timebeat.app/community/platform/initial-configuration),
   and [PTP² Mesh](https://timebeat.app/community/platform/ptpsquared-mesh-basics)
   guides.
3. Save the package, licence, and reviewed configuration as local files on the
   target host. Do not paste their contents into a command line.
4. Run:

```bash
./bin/roko-guided-install --time-stack timebeat --dry-run
./bin/roko-guided-install --time-stack timebeat
```

The Timebeat manifest asks for local paths to the vendor package, licence, and
reviewed configuration. It installs them without copying their contents into
logs, Git, environment files, or a ROKO service unit. ROKO does not redistribute
the package, configuration, or licence.

Timebeat replaces Chrony/ntpd/ptp4l as the system-clock owner. Do not run two
clock-steering daemons at once. The installer fails if a conflicting daemon is
still active after Timebeat starts.

The Timebeat configuration surface is vendor-controlled and requires a
Timebeat sign-in. The ROKO installer deliberately does not guess or synthesize
that proprietary operational configuration. It verifies that the supplied
configuration contains a PTP² section and installs the reviewed file exactly.

## What the installer completes

- platform, architecture, runtime, and disk-capacity preflight;
- Chrony installation and synchronization, or operator-licensed Timebeat
  installation and service activation;
- checksum-verified ROKO native binary or immutable container image;
- testnet chain specification;
- hardened, non-authoring full/archive/observer service;
- interactive ROKO `ptp2` observer-key insertion when that role is selected;
- matching genesis, peers, full sync, stable peer identity, and advancing
  finalized-head verification; and
- a value-free readiness report.

Before any change, the launcher shows the resolved node name, role, runtime,
clock owner, timeout, report location, and ordered steps. Use `--dry-run` to
review this plan. For automated lab provisioning, supply all documented
environment values and use `--non-interactive`; no implicit defaults are used
for missing required values.

The `validator-candidate` role deliberately stops at a fully synchronized
non-authoring peer. Validator session keys, bonding, enrollment, authority-set
activation, and authoring require the separate reviewed operator process:

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
