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

## Before enrollment

- Verify the downloaded ROKO binary and chain specification.
- Finish synchronization and require advancing finalized heads.
- Confirm the node is not reporting the Authority role.
- Keep HTTP RPC on loopback. Never make author methods publicly reachable.
- Establish at least one peer and the documented time policy.
- Intentionally publish the P2P multiaddress other nodes should dial.

## Generate or verify keys

Generate fresh keys:

```bash
bin/roko-validator-enroll \
  --rpc http://127.0.0.1:9944 \
  --binary /usr/local/bin/roko-node \
  --public-address /dns4/validator.example/tcp/30333/p2p/YOUR_PUBLIC_PEER_ID \
  --confirm-new-keys \
  --output roko-validator-enrollment.json
```

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
