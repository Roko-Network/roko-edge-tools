# Validator self-join

The permissionless path is a two-system handoff:

1. This repository installs and verifies the operator-controlled node.
2. `roko-validator-enroll` generates node-owned session keys locally and
   exports only public enrollment facts.
3. The operator imports the file into Agora and uses their own wallet to sign
   lock/bond, `session.setKeys`, and `staking.validate`.
4. Agora follows finalized candidate, waiting, queued, active, authoring,
   maintenance, rotation, and exit state.

If a browser wallet cannot complete enrollment, follow the
[local node-wallet alternative](validator-node-wallet.md). It performs the same
lock, bond, set-keys, and validate sequence from the validator host.

The node and wallet remain separate security domains. Never upload a keystore,
seed phrase, secret URI, node-key bytes, wallet private key, or OpenBao
credential. The enrollment JSON is public but integrity-sensitive and
short-lived; discard it after use and generate a fresh package for rotation.

## Install the enrollment commands

The enrollment CLI is a separate signed edge-tool release, not part of the
`roko-node` binary. The guided validator-candidate installer installs it. For
an already-running node, use the canonical signed-manifest-first sequence:

```bash
mkdir roko-validator-tool && cd roko-validator-tool
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/install-roko-validator-enroll.sh
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/SHA256SUMS
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/SHA256SUMS.asc
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/roko-release-signing-key.asc
export ROKO_VERIFY_GNUPGHOME="$(mktemp -d)"
test "$(GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --with-colons --import-options show-only --import roko-release-signing-key.asc 2>/dev/null | awk -F: '$1=="fpr"{print toupper($10);exit}')" = 62297562B1C7053088F405DB0117DAAA677A5BF2
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --import roko-release-signing-key.asc
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --verify SHA256SUMS.asc SHA256SUMS
awk '$2=="install-roko-validator-enroll.sh"{print}' SHA256SUMS | sha256sum --check --strict
sudo bash install-roko-validator-enroll.sh --release-base https://downloads.roko.network/validator-tools/1.4.6
roko-validator-enroll --version
```

The current release is **tooling 1.4.6**. Its exact qualified pair is Linux
amd64 node release `nightly-f490bcd1-20261014` (source
`f490bcd12df8af67e9bd009482fbc1954199d7f1`) on runtime spec 286; see
[Tooling 1.4.6 compatibility](#tooling-146-compatibility). Earlier releases
qualified older node builds; their records remain in the qualification
evidence. Prefer the already-qualified current node; do not downgrade merely
to match version labels. The [qualification record](guarded-enrollment-qualification.md)
contains binary digests, runtime-code identity and scope. The signed manifest's
older node-line/range fields describe the compatibility envelope; its exact
`qualifiedBuilds` entries describe the executions actually tested. Runtime
285/287 and a custom PHC image are not implied to have passed those tests.

A node display string such as `3.0.0-dev-f490bcd12df` is distinct from the node
release ID and the enrollment-tool version. Verify signed artifact identity
and required RPC capabilities instead of comparing those three strings as
semver. The CLI records binary identity; it does not itself authenticate the
node binary or certify the operator's service configuration.

For an air-gapped host, download the versioned offline bundle and its
`.sha256` file on another host, transfer both files, then verify the pinned
release key fingerprint and the signed `SHA256SUMS` manifest before running the
bundled installer. This does not require cloning a development branch:

```bash
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/roko-validator-enroll-offline-1.4.6.tar.gz
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.6/roko-validator-enroll-offline-1.4.6.tar.gz.sha256
sha256sum --check --strict roko-validator-enroll-offline-1.4.6.tar.gz.sha256
tar -xzf roko-validator-enroll-offline-1.4.6.tar.gz
gpg --import roko-release-signing-key.asc
gpg --fingerprint 62297562B1C7053088F405DB0117DAAA677A5BF2
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum --check --strict --ignore-missing SHA256SUMS
sudo bash install-roko-validator-enroll.sh --bundle-dir "$PWD"
```

The offline `.sha256` sidecar must name only the archive basename so
`sha256sum --check --strict` works from the download directory on another host.
Older builders embedded the build path; that failure does not establish archive
corruption. Do not skip authentication: the standalone sidecar is not a
signature, and installation still requires the pinned release key and signed
manifest checks above. Tooling 1.4.0 is the first verified fixed release. The affected v1.1.0 and
v1.3.0 assets remain unchanged; see [asset evidence](offline-checksum-qualification.md).

## Tooling 1.4.6 compatibility

Tooling 1.4.6 accepts exactly runtime spec **286**, the network's live runtime.
Tooling 1.4.5 covered runtime specs 285–287; a future runtime upgrade requires
a new tooling release with its own fixture. The profile's single qualified
build is the node the managed fleet runs:

| Field | Value |
|---|---|
| Node release | `nightly-f490bcd1-20261014` |
| Source revision | `f490bcd12df8af67e9bd009482fbc1954199d7f1` |
| Version string | `3.0.0-dev-f490bcd12df` |
| amd64 `roko-node` SHA-256 | `b0ddc0fdae81ce09b1f6c9b18eee61f86ab6d35ec53b825bcfcc77acf3e66fdc` |

The [guarded fixture](evidence/guarded-f490bcd-runtime286-20261015.json)
covers generation, reuse, the Agora import and rejection cases, and fault
recovery. The signed 1.4.6 installation then passed the same fixture in
delivery mode.

**arm64 (for example NVIDIA Jetson).** The same node release publishes an arm64
build (`roko-node-testnet-linux-arm64.tar.gz`, inner `roko-node` SHA-256
`272d20659a047a530280a4fa9018cf16f450ec3fffecb3b669af336856a74fc2`). It has not
yet run the enrollment fixture, so the profile makes no arm64 claim. The
enrollment commands are architecture-independent and the procedure is the
same. Two arm64 constraints apply:

- The arm64 binary requires glibc 2.34 or newer: Ubuntu 22.04 or later, or
  JetPack 6 or later on Jetson. JetPack 5 (glibc 2.31) cannot run it.
- `roko-validator-enroll --binary` executes the binary to record its identity.
  Enrollment therefore needs a runnable native `roko-node` on the host, even
  when the node itself runs in Docker.

The runtime 290
[candidate fixture](evidence/guarded-fba4-runtime290-candidate-20261015.json)
is historical evidence for a runtime that is not active on the network. See the
[qualification sequence](private-enrollment-qualification.md).

## Before enrollment

The guarded window requires a proven RPC policy: the enrollment CLI uses a
well-formed dummy `author_hasKey` lookup and accepts only a boolean response or
the node's explicit Safe denial. Exit 0 means Safe, exit 2 means accessible key
RPC, and exit 1 means the check is inconclusive. An arbitrary error must not be
treated as permission to generate keys. See the [qualification record](rpc-policy-qualification.md)
for tested builds and signed-release evidence. Complete the
[existing-install preflight](existing-install-enrollment-preflight.md) before
any restart or key operation.

- Verify the downloaded ROKO binary and chain specification.
- Finish synchronization and require advancing finalized heads.
- Confirm the node is not reporting the Authority role.
- Keep HTTP RPC on loopback. Never make author methods publicly reachable.
- Establish the public boot peer for synchronization and, for validator
  candidates, the two mapped active-authority peers from the signed public
  authority manifest. Generic peers do not satisfy temporal quorum.
- Inbound P2P is optional. `--public-address` is optional: without it the CLI
  uses the node's listen addresses. Outbound-only candidates, including NAT and
  WiFi hosts, are supported and need no port-forward. A stable outbound path
  to the mapped authorities matters more than inbound reachability. If you do
  publish an address, use `/dns4/HOST/tcp/30333/p2p/PEER_ID` or
  `/ip4/A.B.C.D/tcp/30333/p2p/PEER_ID`.

### Docker time-source contract

The supported guided Docker path downloads the architecture-specific offline
image from `downloads.roko.network/releases/current`, verifies both the release
checksum and the image's source-revision label, and records the immutable local
image ID. It does not depend on a moving registry tag.

The installed service requires the host Chrony command socket at
`/run/chrony/chronyd.sock`. It mounts `/run/chrony` read/write because
`chronyc` creates its client datagram socket in that directory, adds the host
socket's numeric group to container uid 1000, and passes both
`--timesync-time-source auto` and
`--timesync-chrony-socket /run/chrony/chronyd.sock`. Before every start it
proves the image contains `chronyc` and `ethtool` but no independent
`chronyd`; the host remains the only system-clock owner.

Inspect the installed contract without changing the host:

```bash
ROKO_CHRONY_GID="$(stat -c %g /run/chrony/chronyd.sock)" \
  installer/scripts/install-roko-service.sh \
  --runtime docker --node-name preview --clock-provider chrony --render-unit
```

`No chrony or PPS device detected` after installing this contract is a hard
failure. Confirm the service still contains the mount, group and explicit
flags; confirm the socket exists; and reinstall the current image rather than
adding `chronyd` inside the container.

### Validator timing participation profile

The node flag `--timesync-participation-profile` selects how a validator
responds to timing-quality changes. It takes `early-testnet` or `strict`; the
node binary itself defaults to `strict` when the flag is absent.

- `early-testnet` is the installer default for the `validator-candidate` role
  on the configured ROKO testnet (`roko-testnet-v2`). Per ADR-021 the early
  configured testnet must let elected validators with imperfect timing quality
  keep participating while their operators diagnose hardware and networks, and
  every network-managed validator runs this profile. Ordinary mesh-quality
  settling or convergence regression is reported as a warning instead of
  stopping authoring.
- `strict` is opt-in. Authoring stops (`STRICT_TIMING_UNQUALIFIED`) whenever
  timing quality falls below the strict qualification threshold.

Neither profile bypasses mandatory evidence: full sync, fresh authenticated
authority updates, a disciplined system clock, and active session keys remain
required under `early-testnet` exactly as under `strict`.

Select the profile at install time with `--timing-profile early-testnet|strict`
(or `ROKO_TIMING_PROFILE`) on `bin/roko-guided-install` or
`installer/scripts/install-roko-service.sh`. Only the `validator-candidate`
role renders the flag; full, archive, and observer units never receive it, and
passing `--timing-profile` for those roles is rejected. Preview the result:

```bash
ROKO_CHRONY_GID="$(stat -c %g /run/chrony/chronyd.sock)" \
ROKO_AUTHORITY_ADDRESSES="$(python3 -c 'import json; [print(a) for x in json.load(open("/etc/roko/authority-peers.json"))["authorities"] for a in x["addresses"]]')" \
  installer/scripts/install-roko-service.sh \
  --runtime native --node-name preview --clock-provider chrony \
  --validator-candidate --timing-profile early-testnet --render-unit
```

#### Switching an already-installed validator

Validators installed before this option exist without the flag and therefore
run the node default, `strict`. To switch, either rerun the service installer
with the same arguments you used originally (it rewrites
`/etc/systemd/system/roko-node.service` and preserves keys and data), or edit
the unit by hand:

1. `sudo systemctl edit --full roko-node.service`
2. In `ExecStart`, add `  --timesync-participation-profile early-testnet \`
   next to the other `--timesync-*` lines (use `strict` to opt back in). For
   the Docker unit the line goes among the node arguments after `${ROKO_IMAGE}`.
3. `sudo systemctl daemon-reload && sudo systemctl restart roko-node`
4. Confirm with `systemctl cat roko-node | grep participation-profile` and the
   node log.

No session-key, keystore, or database change is needed; the profile is read
at startup only.

### Temporal mesh thresholds

Every rendered unit, for every role, carries the fleet temporal-mesh policy:

```text
  --timesync-convergence-threshold-ns 5000000 \
  --timesync-lucky-threshold-ns 10000000 \
```

The testnet mesh is routed and software-timestamped, so peers normally differ
by a few milliseconds. The network-managed validators and the public sentry run
a 5 ms convergence threshold with a 10 ms lucky-packet/reputation tolerance.
Without these flags the node falls back to 1 ms and 100 us, so ordinary WAN
spread between authorities reports `Converging` with timing quality 0. Under
the `strict` profile that stops authoring. Under `early-testnet` it produces
constant timing warnings and makes quality readings incomparable with the
rest of the fleet.

Units installed by tooling before 1.4.5 lack both lines, and their `--bootnodes`
address carries a `/ws` segment that matches no listener on the public
bootnode. To update an existing install, rerun the service installer with your
original arguments, or edit the unit by hand:

1. `sudo systemctl edit --full roko-node.service`
2. Add the two lines above next to the other `--timesync-*` lines. In
   `--bootnodes`, change `/tcp/30333/ws/p2p/` to `/tcp/30333/p2p/`.
3. `sudo systemctl daemon-reload && sudo systemctl restart roko-node`

No session-key, keystore, or database change is needed.

## Generate or verify keys

The installed node correctly defaults to `--rpc-methods Safe`; therefore a
direct `author_rotateKeys` request is rejected. Do not make RPC public to work
around that control. For the supported systemd service, use the guarded local
window:

```bash
sudo roko-session-key-window \
  --confirm-isolated-window \
  --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --output roko-validator-enrollment.json
```

The helper runs the enrollment CLI itself; everything after `--` is passed to
`roko-validator-enroll`. Do not run a separate enrollment first. Add
`--public-address` only if you intentionally publish a dialable address. Pass
`--service NAME.service` when the unit is not `roko-node.service`.

### Service unit contract

The helper refuses a unit that hardcodes `--rpc-methods Safe`. It requires all
of the following:

- `/etc/roko/node-rpc.env` is a regular file owned by root, not group- or
  world-writable, containing exactly `ROKO_RPC_METHODS=Safe`;
- the unit contains `Environment=ROKO_RPC_METHODS=Safe` and
  `EnvironmentFile=-/etc/roko/node-rpc.env`;
- `ExecStart` contains the literal `--rpc-methods ${ROKO_RPC_METHODS}`;
- no `--rpc-external`, `--unsafe-rpc-external` or wildcard
  `--rpc-listen-address`;
- the service is active.

Units rendered by `installer/scripts/install-roko-service.sh` in tooling 1.4.6
still hardcode `--rpc-methods Safe` and do not create the policy file. Adapt
them before opening the window. The adaptation is the contract used by the
qualification fixture:

```bash
systemctl cat roko-node.service > roko-node.service.before
python3 - /etc/systemd/system/roko-node.service roko-node.service <<'PY2'
import sys
s = open(sys.argv[1]).read()
assert s.count('  --rpc-methods Safe\n') == 1, 'expected exactly one --rpc-methods Safe line'
s = s.replace('  --rpc-methods Safe\n', '  --rpc-methods ${ROKO_RPC_METHODS}\n')
s = s.replace('[Service]\n', '[Service]\nEnvironment=ROKO_RPC_METHODS=Safe\nEnvironmentFile=-/etc/roko/node-rpc.env\n', 1)
open(sys.argv[2], 'w').write(s)
PY2
printf 'ROKO_RPC_METHODS=Safe\n' > node-rpc.env
sudo install -D -m 0600 -o root -g root node-rpc.env /etc/roko/node-rpc.env
sudo install -m 0644 -o root -g root roko-node.service /etc/systemd/system/roko-node.service
sudo systemctl daemon-reload && sudo systemctl restart roko-node
systemctl cat roko-node.service | grep -F -- '--rpc-methods ${ROKO_RPC_METHODS}'
```

Expected: the last command prints the `--rpc-methods ${ROKO_RPC_METHODS}` line.
Wait for the node to resync, then confirm `--check-rpc-policy` exits 0 (below)
before opening the window. For a custom unit, make the same three-line change
by hand. Keep its other settings, as recorded in the
[existing-install preflight](existing-install-enrollment-preflight.md).

Before confirming, prove there is no reverse proxy, SSH tunnel, VPN port
forward, container publisher, or other relay exposing the local RPC port. The
helper requires the exact supported unit contract, an active service, an owned
non-writable policy file initially set to Safe, and a listener that the
enrollment CLI proves loopback-only. It creates a timestamped backup, switches
only the policy value, restarts the service, generates keys, and restores Safe
even when generation fails or the process is interrupted. If restoration or
health verification fails, it leaves Safe on disk, stops the service, and
reports the retained recovery backup instead of claiming success.

Verify Safe restoration independently after any manual workflow:

```bash
roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --check-rpc-policy
```

The command performs a non-mutating, well-formed dummy `author_hasKey` lookup.
The supported Safe response is distinguished from transport failure, malformed
JSON, an unavailable health endpoint, and other RPC rejection. Exit `0` with
`safe-restored` is required before package import. Exit `2` means key-management
RPC remains accessible.

### Reissue a package for an existing tuple

The CLI's `--session-keys` mode verifies custody without calling
`author_rotateKeys`. That custody RPC is also gated by Safe policy on the
qualified builds; a direct command against a Safe node is not a complete
refresh procedure. Never rotate solely because a package expired.

Tooling **1.4.1** adds the [qualified guarded reuse option](guarded-reuse-qualification.md)
below. Tooling 1.4.0 supports generation only in the helper. The reuse path
keeps the same non-authoring, isolation, backup and exact Safe restoration
controls:

```bash
sudo roko-session-key-window \
  --reuse-session-keys 0xPUBLIC_ENCODED_KEYS \
  --confirm-isolated-window --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --output roko-validator-enrollment-refreshed.json
```

Use the unchanged public tuple from the previous package or authenticated
finalized account record. A custody failure stops the operation; it never falls
back to generation. Keep the old package for comparison, use a new output file,
and compare tuple identity before import. A new package ID/expiry does not mean
new keys or a finalized registration.

The v1 contract explicitly uses ROKO's current `legacy-empty` session-key
proof. The CLI and Agora both metadata-check this boundary. They will reject an
unsupported proof mode rather than silently reinterpret it.

If direct key generation reports `Session-key generation is disabled by the
node's Safe RPC policy`, that is the expected security boundary. Use the
guarded helper above, or use the qualified guarded reuse path in tooling 1.4.1 or later. Do not
change the public `rpc.roko.network` service and do not send node keys to a
wallet, Agora, or support.

## Join and monitor

The guided installer verifies and consumes the short-lived signed manifest at
<https://nodes.roko.network/authority-peers.json>. Each listed multiaddress is
publicly routable, ends in the advertised active authority's libp2p peer ID,
and is configured as a reserved peer. The manifest contains only public
account, peer and finalized-session facts; internal addresses are prohibited.
If it expires or its signature, genesis, active accounts, peer IDs, or minimum
gate do not validate, stop and refresh it before candidacy.

Open <https://agora.roko.network/participate/staking>, import the package,
connect the staking account, and inspect each transaction preview. A finalized
`staking.validate` call means candidate intent only. Wait for separately
reported election, active-session membership, authored finalized blocks, and
finality evidence.

After the wallet calls finalize, prove that the same public tuple is held by
this node and registered at a finalized head before enabling validator mode:

```bash
roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --check-account 0xYOUR_STASH_ACCOUNT \
  --expected-session-keys 0xPUBLIC_ENCODED_KEYS
```

Exit status `0` means the node has local custody and finalized bond, intent,
and matching next-session keys. Exit status `2` is a normal not-ready result;
inspect the value-free JSON fields and wait or correct the missing step. It
does not mean the validator is elected or authoring. Agora separately proves
active-session membership and recent finalized authorship.

Capture the node-local proof requested by Agora with the installed command:

```bash
roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --save-readiness ./roko-validator-readiness.json
```

This uses the Safe `temporal_getValidatorReadiness` method and writes its
validated redacted result, not a JSON-RPC wrapper. Import that file in Agora's
**Import validator readiness** panel. It contains public session identifiers,
finalized lifecycle facts, aggregate peer classes, convergence, remediation,
and optional finalized authorship evidence. It cannot contain seeds, private
key bytes, peer addresses, or secret paths. Never assemble or edit this proof
by hand. If the command reports that the method is absent, install the current
checksum-verified ROKO node release and confirm `rpc_methods` lists it.

## Rotate and exit

Create a fresh package to rotate keys. Do not purge old keys until Agora proves
the replacement is active and authoring. To exit, chill first, then unbond,
wait for the finalized bonding period, withdraw matured funds, and stop/purge
only after the product reports the safe state.
