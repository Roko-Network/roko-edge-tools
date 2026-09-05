<p align="center">
  <a href="https://nodes.roko.network/edge/">
    <img src="assets/roko-logo.png" width="104" height="104" alt="ROKO Network">
  </a>
</p>

<h1 align="center">ROKO Edge Tools</h1>

<p align="center">
  Operator-first health, installation, diagnostics, and reporting tools for infrastructure you control.
</p>

<p align="center">
  <a href="https://nodes.roko.network/edge/">Edge guide</a>
  ·
  <a href="https://time.roko.network/">ROKO Time</a>
  ·
  <a href="https://docs.roko.network/">Documentation</a>
</p>

---

This is the only public repository required by these optional diagnostics. The
node itself is distributed as either:

- an architecture-specific public image at
  `ghcr.io/roko-network/roko-node:testnet-latest-{amd64,arm64}`; or
- a checksum-verified native binary from
  [downloads.roko.network](https://downloads.roko.network/), also available
  through the [peer-assisted download guide](https://downloads.roko.network/torrent).

Node operation does not require access to the private source repository. See
[nodes.roko.network](https://nodes.roko.network/) for the current runbook.
For source selection, clock architecture, hobbyist/professional deployment,
Timebeat, security, verification, and recovery, start with the
[ROKO Time Authority docset](docs/time-authority/README.md). Its metadata and
Pagenbar links support deterministic agent traversal without requiring AIWG.
The recommended node setup path is to download the checksum manifest and reviewed
one-off scripts and their
[checksum manifest](https://downloads.roko.network/scripts/SHA256SUMS),
verify them locally, inspect them, and then run the native or Docker workflow.
Do not pipe a remote script directly into a shell. Offline Docker archives are
available by HTTPS and through the official torrent for registry-free setup.

The validator enrollment CLI is also a signed, versioned release artifact. It
does not require a development clone. Verify the pinned release key and signed
checksum manifest before executing the canonical installer:

```bash
mkdir roko-validator-tool && cd roko-validator-tool
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/current/install-roko-validator-enroll.sh
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/current/SHA256SUMS
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/current/SHA256SUMS.asc
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/current/roko-release-signing-key.asc
export ROKO_VERIFY_GNUPGHOME="$(mktemp -d)"
test "$(GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --with-colons --import-options show-only --import roko-release-signing-key.asc 2>/dev/null | awk -F: '$1=="fpr"{print toupper($10);exit}')" = 62297562B1C7053088F405DB0117DAAA677A5BF2
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --import roko-release-signing-key.asc
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --verify SHA256SUMS.asc SHA256SUMS
awk '$2=="install-roko-validator-enroll.sh"{print}' SHA256SUMS | sha256sum --check --strict
sudo bash install-roko-validator-enroll.sh
roko-validator-enroll --version
```

The command sequence and installer verify the signed checksum manifest and signed release metadata
with the pinned ROKO release key before installing anything. The offline bundle
at the same location contains the archive, signatures, public key, metadata,
and installer; extract it and pass its directory with `--bundle-dir`.

The tools are intentionally dependency-light:

- Bash for host/service/time checks
- Python 3 standard library for JSON-RPC probes
- No secrets
- No writes unless you explicitly copy example config into your host

## Quick start

```bash
git clone https://github.com/Roko-Network/roko-edge-tools.git
cd roko-edge-tools

./bin/roko-edge-doctor
./bin/roko-rpc-health --rpc http://127.0.0.1:9944
./bin/roko-time-health
```

For a guided full, archive, observer, or validator-candidate installation:

```bash
./bin/roko-guided-install --time-stack chrony --dry-run
./bin/roko-guided-install --time-stack chrony
```

Before choosing a region or timing stack, read
[`docs/time-authority/README.md`](docs/time-authority/README.md). It routes
humans and agents to focused pages rather than requiring a repository-wide
crawl.

Every role joins the live ROKO chain P2P network. Choose `observer` to
advertise authenticated measurements on ROKO's built-in PTP² protocol. Choose
`--time-stack timebeat` for the separate licensed Timebeat PTP² Mesh. An
`observer` using Timebeat participates in both PTP² layers while remaining a
non-authoring ROKO node until separately enrolled.

Operators using Timebeat can select `--time-stack timebeat`; they must obtain
the pinned 2.3.5 package and per-node licence from
[timebeat.app](https://www.timebeat.app/downloads/software). The installer
collects the local package, licence, and reviewed PTP Squared configuration
paths and performs the remaining installation and verification steps. See the
[agentic installer guide](installer/README.md).

## Tools

| Tool | Purpose |
|---|---|
| `bin/roko-edge-doctor` | One-shot local node, service, RPC, disk, network, and Chrony health summary |
| `bin/roko-rpc-health` | JSON-RPC health probe for local or public ROKO RPC |
| `bin/roko-time-health` | Chrony/system clock diagnostics for NTP and edge time hosts |
| `bin/roko-node-tail` | Convenience log tail for a systemd-managed node |
| `bin/roko-edge-report` | Generate a sanitized support bundle |
| `bin/roko-seed-refresh` | Add current ROKO snapshot/release torrents to Transmission and verify completed payloads |
| `bin/roko-guided-install` | Run the self-contained AIWG-manifested installer for Chrony or operator-licensed Timebeat deployments |
| `bin/roko-validator-enroll` | Verify a synced non-authoring validator candidate, generate or verify node-owned session keys over loopback, and export a short-lived public enrollment package for Agora |
| `bin/roko-session-key-window` | Open one guarded loopback-only Unsafe RPC window for session-key generation, then restore and prove Safe policy before handoff |

## Permissionless validator enrollment

Finish the guided `validator-candidate` installation first. The node must
remain non-authoring, fully synchronized, peered, finalizing, and
time-synchronized. The supported service starts with `--rpc-methods Safe`,
which correctly blocks `author_rotateKeys`. Generate a fresh public enrollment
package through the guarded local window:

The guided installer installs and prints the exact command path and version.
For a standalone or existing node, use the checksum-verifying command above;
do not hunt for this tool in the node binary archive or clone a development
branch.

```bash
sudo ./bin/roko-session-key-window \
  --confirm-isolated-window \
  --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --public-address /dns4/validator.example/tcp/30333/p2p/YOUR_PUBLIC_PEER_ID \
  --output ./roko-validator-enrollment.json
```

The two confirmations attest that the operator reviewed the temporary change
and that no tunnel, reverse proxy, or port forward publishes the loopback RPC.
Every invocation creates a new session-key tuple in the local node keystore.
The helper retains a timestamped recovery backup, fails closed on a public
listener or unsupported service contract, and stops the service if Safe-mode
recovery cannot be proven. To verify an already generated public tuple without
rotating again, use `roko-validator-enroll --session-keys 0x...`.

After any manual policy change, prove restoration independently:

```bash
./bin/roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --check-rpc-policy
```

Exit `0` and state `safe-restored` prove key-management RPC is blocked while
safe health RPC remains available. Exit `2` means Unsafe remains accessible;
do not import the package or enable validator mode.

The command:

- refuses non-loopback or externally bound author RPC;
- checks genesis, runtime metadata, binary digest, clock, peers, sync,
  persistent peer ID, non-authoring role, and advancing finality;
- requires `author_hasSessionKeys` to prove local custody;
- writes the package with mode `0600` and a canonical SHA-256 digest; and
- allow-lists public facts so private keys, keystores, seeds, wallet
  authorization, and OpenBao material cannot enter the package.

Import the resulting file at
[agora.roko.network/participate/staking](https://agora.roko.network/participate/staking).
Agora validates the file against the connected chain before asking your wallet
to review any staking call. Creating the file does not bond funds, register
keys on chain, declare validator intent, guarantee election, or activate
authoring.

## Common environment variables

```bash
export ROKO_RPC_URL=http://127.0.0.1:9944
export ROKO_SERVICE=roko-node
export ROKO_BASE_PATH=/var/lib/roko
export ROKO_NTP_SOURCE=ntp01.roko.network
export ROKO_SEED_DIR=/srv/roko-seed
export ROKO_SEED_PROFILES="normal releases"
```

`ntp01.roko.network` is currently available as an optional public bootstrap
and consistency source. It is not a substitute for independent Stratum 1/2
authorities. The guided installer offers regional source profiles and requires
Chrony to select at least two sources.

## BitTorrent seeding

Seeders help distribute public snapshots and node release bundles. They do not
need validator keys, wallet material, private source access, or exposed RPC.

```bash
sudo install -d -o debian-transmission -g debian-transmission \
  /srv/roko-seed/snapshots /srv/roko-seed/releases
./bin/roko-seed-refresh
```

The default profiles seed the current normal snapshot and current node release
bundle. Add `archive` only when you have enough disk and bandwidth:

```bash
ROKO_SEED_PROFILES="normal archive releases" ./bin/roko-seed-refresh
```

For unattended refresh, install
`examples/roko-seed-refresh.service` and
`examples/roko-seed-refresh.timer` to `/etc/systemd/system/`, then enable the
timer. See the public guide at
[docs.roko.network](https://docs.roko.network/#bittorrent-seeding).

## Safety boundaries

- The guided observer flow inserts one ROKO `ptp2` key interactively; it never
  places the secret in argv, a manifest, or a report.
- The guided installer does not generate validator session keys. The separate
  guarded session-key window creates them only in the local node keystore after
  two explicit operator confirmations, restores Safe RPC, and never enables
  authoring or exports private key material.
- Timebeat software and licences remain vendor/operator supplied and are never
  redistributed by ROKO; the non-secret ROKO mesh profile is bundled here.
- The installer performs the host, clock, ROKO runtime, service, observer-key,
  synchronization, finality, and readiness-report steps. It does not guess a
  vendor Timebeat configuration or activate validator authority.
- It does not expose RPC or NTP services.
- It does not change firewall rules.
- It does not delete old torrent data automatically.

Use it to observe and report; make operational changes deliberately.

## Mirrors

- Primary: [github.com/Roko-Network/roko-edge-tools](https://github.com/Roko-Network/roko-edge-tools)
- Mirror: [git.integrolabs.net/roctinam/roko-edge-tools](https://git.integrolabs.net/roctinam/roko-edge-tools)
