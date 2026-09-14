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
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.0/install-roko-validator-enroll.sh
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.0/SHA256SUMS
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.0/SHA256SUMS.asc
curl --fail --location --remote-name https://downloads.roko.network/validator-tools/1.4.0/roko-release-signing-key.asc
export ROKO_VERIFY_GNUPGHOME="$(mktemp -d)"
test "$(GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --with-colons --import-options show-only --import roko-release-signing-key.asc 2>/dev/null | awk -F: '$1=="fpr"{print toupper($10);exit}')" = 62297562B1C7053088F405DB0117DAAA677A5BF2
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --import roko-release-signing-key.asc
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --verify SHA256SUMS.asc SHA256SUMS
awk '$2=="install-roko-validator-enroll.sh"{print}' SHA256SUMS | sha256sum --check --strict
sudo bash install-roko-validator-enroll.sh --release-base https://downloads.roko.network/validator-tools/1.4.0
roko-validator-enroll --version
```

The first signed release fixing both the guarded probe and portable offline
checksum is **tooling 1.4.0**. The exact qualified Linux amd64 pairs use runtime
286 and either node source `086baf26c0e0db666526b8f649269facd1c37da7`
(`nightly-086baf26-20260913`) or `be8920f47d282da73297c17875791c4e3d444625`
(`v1.1.0`). Prefer the already-qualified current node; do not downgrade merely
to match version labels. The [qualification record](guarded-enrollment-qualification.md)
contains binary digests, runtime-code identity and scope. The signed manifest's
older node-line/range fields describe the compatibility envelope; its exact
`qualifiedBuilds` entries describe the executions actually tested. Runtime
285/287 and a custom PHC image are not implied to have passed those tests.

A node display string such as `3.0.0-dev-086baf26c0e` is distinct from the node
release ID and the enrollment-tool version. Verify signed artifact identity
and required RPC capabilities instead of comparing those three strings as
semver. The CLI records binary identity; it does not itself authenticate the
node binary or certify the operator's service configuration.

For an air-gapped host,
download the versioned offline bundle and its `.sha256` file on another host,
verify the bundle over a separately authenticated channel, transfer both,
extract the bundle, verify its pinned key plus `SHA256SUMS.asc`, and run:

```bash
sudo bash install-roko-validator-enroll.sh --bundle-dir "$PWD"
```

The offline `.sha256` sidecar must name only the archive basename so
`sha256sum --check --strict` works from the download directory on another host.
Older builders embedded the build path; that failure does not establish archive
corruption. Do not skip authentication: the standalone sidecar is not a
signature, and installation still requires the pinned release key and signed
manifest checks above. Tooling 1.4.0 is the first verified fixed release. The affected v1.1.0 and
v1.3.0 assets remain unchanged; see [asset evidence](offline-checksum-qualification.md).

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
- Intentionally publish the P2P multiaddress other nodes should dial.

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

## Generate or verify keys

The installed node correctly defaults to `--rpc-methods Safe`; therefore a
direct `author_rotateKeys` request is rejected. Do not make RPC public to work
around that control. For the supported systemd service, use the guarded local
window:

```bash
sudo bin/roko-session-key-window \
  --confirm-isolated-window \
  --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --public-address /dns4/validator.example/tcp/30333/p2p/YOUR_PUBLIC_PEER_ID \
  --output roko-validator-enrollment.json
```

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
bin/roko-validator-enroll \
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

The [qualified source candidate](guarded-reuse-qualification.md) adds the helper option below. **It is not included in
signed tooling 1.4.0; wait for its signed release before using it on an operator
host.** The helper keeps the same non-authoring, isolation, backup and exact
Safe restoration controls:

```bash
sudo bin/roko-session-key-window \
  --reuse-session-keys 0xPUBLIC_ENCODED_KEYS \
  --confirm-isolated-window --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --public-address /dns4/validator.example/tcp/30333/p2p/YOUR_PUBLIC_PEER_ID \
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
guarded helper above, or use the qualified guarded reuse path once released. Do not
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
bin/roko-validator-enroll \
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
