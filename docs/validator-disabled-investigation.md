# Disabled validator investigation — 2026-09-14

Public reports: [#18](https://github.com/Roko-Network/roko-edge-tools/issues/18)
and [#12](https://github.com/Roko-Network/roko-edge-tools/issues/12).

## Verified finalized history

Read-only queries to `https://rpc.roko.network` used pinned finalized hashes on
genesis `0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb`.
The runtime reports spec version 286. Validator index 0 is
`0x162B8D18097E96d6C754F11396Bb4c9463Dad2d0` throughout the observed window.
[Full public receipt](evidence/validator18-session-history-20260914.json)
contains each block hash, validator set, session/era, both disabled lists,
heartbeat receipts, authorship counts, and boundary events.

| Block | Session | Active era | Session/Staking disabled indices | Index 0 heartbeat/authored count |
| --- | --- | --- | --- | --- |
| 1215514 | 1178 | 200 | `[0]` / `[0]` | absent / 0 |
| 1215515 | 1179 | 201 | `[]` / `[]` | absent / 0 |
| 1216382 | 1179 | 201 | `[]` / `[]` | absent / 0 |
| 1216383 | 1180 | 201 | `[0]` / `[0]` | absent / 0 |
| 1219801 | 1183 | 201 | `[0]` / `[0]` | absent / 0 |
| 1220028 | 1184 | 201 | `[0]` / `[0]` | absent / 0 |

The disable cleared at the era transition. The validator remained without
accepted heartbeat or authored-block evidence through that enabled session,
and the next session boundary disabled it again. Every observed boundary from
1179 through 1184 reports this account in `imOnline.SomeOffline`, a staking
`SlashReported` event with zero fraction, and an `offences.Offence` of kind
`im-online:offlin`. A zero-fraction report is not proof that funds were deducted.

Snapshots immediately **before** each boundary show no accepted heartbeat for
index 0 in completed sessions 1178–1183. This is stronger than querying an old
session after rotation: im-online clears the previous session's receipt and
authorship maps during rotation. Other validators have nonzero authored-block
counts, which themselves count as online evidence and explain why their
heartbeat receipts can also be absent.

This independently confirms absent accepted heartbeats in the bounded window.
It does not verify all 90 reported sessions or establish where the reporter's
locally queued transaction stops progressing.

## Source interpretation and remaining diagnosis

The node's locked SDK revision is
`d5160c1d567cc73c7df6c816d41e21aa3adb188d`:

- [Session rotation](https://github.com/paritytech/polkadot-sdk/blob/d5160c1d567cc73c7df6c816d41e21aa3adb188d/substrate/frame/session/src/lib.rs#L610)
  clears the session disabled list when the queued set changes.
- [Staking lifecycle](https://github.com/paritytech/polkadot-sdk/blob/d5160c1d567cc73c7df6c816d41e21aa3adb188d/substrate/frame/staking/src/pallet/impls.rs#L492)
  reapplies staking-disabled indices on session start and clears its list at
  era end. The observed transition is consistent with this lifecycle.
- [Heartbeat validation](https://github.com/paritytech/polkadot-sdk/blob/d5160c1d567cc73c7df6c816d41e21aa3adb188d/substrate/frame/im-online/src/lib.rs#L451)
  checks online status, session, authority index, validator count, and signature.
  It does not reject a heartbeat merely because its validator is disabled.
  Valid heartbeats provide a tag for the session and authority.
- The node's vendored pool rejects replacements whose priority is equal to or
  below the transaction already providing that tag. Im-online uses maximum
  priority. Thus the reported equal-maximum priority message is consistent
  with a competing heartbeat already in the local pool; it is not by itself
  proof that the first heartbeat was never admitted or that peers rejected it.

Source inspection is not a substitute for executing validation of the actual
heartbeat against the deployed runtime. The next decisive trace needs the
public transaction hash, decoded session/index, current runtime validity, and
propagation/inclusion observations on the sender and a receiving author.
Preserve the first queued heartbeat when diagnosing replacement errors. Do not
change heartbeat priority, disable authentication, or clear the transaction
pool just to suppress the duplicate message.

`chill` and `validate` change staking intent; no verified recovery procedure
here requires them. The observed era transition already gave this validator
an enabled session, so cycling intent alone does not address absent liveness
evidence. No account transaction, key change, or storage edit was performed.

## Catch-up and temporal transport remain separate

The report of canonical-hash agreement, repeated `Not requested block data`
bans, and recovery only after database deletion is still operator-supplied
evidence. No copy of that old database or reproducible catch-up fixture was
available in this inspection. A supported database-preserving repair has not
been qualified here. Retain chain/Frontier databases and logs for diagnosis;
do not present database deletion, identity replacement, or ban bypass as a
routine recovery procedure.

The #12 correction that reserved peers do reconnect remains incorporated.
Generic connectivity does not prove authenticated temporal quorum. The report
of one mapped source after the rebuild is progress, but does not meet the
reported minimum of two or prove sustained authorship through both relays.

This investigation changed documentation only. No infrastructure or CMDB
activation state changed. Both issues remain open for implementation and
end-to-end recovery qualification.
