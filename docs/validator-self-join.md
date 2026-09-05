# Validator self-join

The permissionless path is a two-system handoff:

1. This repository installs and verifies the operator-controlled node.
2. `roko-validator-enroll` generates node-owned session keys locally and
   exports only public enrollment facts.
3. The operator imports the file into Agora and uses their own wallet to sign
   lock/bond, `session.setKeys`, and `staking.validate`.
4. Agora follows finalized candidate, waiting, queued, active, authoring,
   maintenance, rotation, and exit state.

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

The signed compatibility manifest binds the installed tool revision to chain
ID 52370, the exact testnet genesis, the testnet-v1.1 node line, and runtime
spec versions 285 through 287. The installer rejects signature, checksum,
revision, network, or compatibility mismatches. For an air-gapped host,
download the versioned offline bundle and its `.sha256` file on another host,
verify the bundle over a separately authenticated channel, transfer both,
extract the bundle, verify its pinned key plus `SHA256SUMS.asc`, and run:

```bash
sudo bash install-roko-validator-enroll.sh --bundle-dir "$PWD"
```

## Before enrollment

- Verify the downloaded ROKO binary and chain specification.
- Finish synchronization and require advancing finalized heads.
- Confirm the node is not reporting the Authority role.
- Keep HTTP RPC on loopback. Never make author methods publicly reachable.
- Establish at least one peer and the documented time policy.
- Intentionally publish the P2P multiaddress other nodes should dial.

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

The command performs a non-mutating `author_hasSessionKeys(0x)` policy probe.
The supported Safe response is distinguished from transport failure, malformed
JSON, an unavailable health endpoint, and other RPC rejection. Exit `0` with
`safe-restored` is required before package import. Exit `2` means key-management
RPC remains accessible.

Verify a known public tuple without rotating:

```bash
bin/roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --binary /usr/local/bin/roko-node \
  --session-keys 0xPUBLIC_ENCODED_KEYS \
  --output roko-validator-enrollment.json
```

The v1 contract explicitly uses ROKO's current `legacy-empty` session-key
proof. The CLI and Agora both metadata-check this boundary. They will reject an
unsupported proof mode rather than silently reinterpret it.

If direct key generation reports `Session-key generation is disabled by the
node's Safe RPC policy`, that is the expected security boundary. Use the
guarded helper above, or verify a public tuple that already exists. Do not
change the public `rpc.roko.network` service and do not send node keys to a
wallet, Agora, or support.

## Join and monitor

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

## Rotate and exit

Create a fresh package to rotate keys. Do not purge old keys until Agora proves
the replacement is active and authoring. To exit, chill first, then unbond,
wait for the finalized bonding period, withdraw matured funds, and stop/purge
only after the product reports the safe state.
