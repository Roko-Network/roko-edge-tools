# RPC policy qualification — 2026-09-14

Issue: https://github.com/Roko-Network/roko-edge-tools/issues/14

The policy check now makes the well-formed, non-mutating request
`author_hasKey("0x" + 32 zero bytes, "babe")`. Either boolean result establishes
that the lookup was dispatched. Under Safe, only the explicit message
`RPC call is unsafe to be called externally` with code -32601 or 1040 proves
policy denial. Missing methods, generic access-denied messages, argument errors,
unknown errors, non-boolean results, malformed or mismatched JSON-RPC envelopes,
and transport failures are inconclusive. They cannot authorize generation or
prove Safe restoration.

The locked [SDK implementation](https://github.com/paritytech/polkadot-sdk/blob/d5160c1d567cc73c7df6c816d41e21aa3adb188d/substrate/client/rpc/src/author/mod.rs#L145)
checks `DenyUnsafe` before this keystore lookup. Unlike the former empty
`author_hasSessionKeys` request, it does not depend on runtime session-tuple
decoding. In particular, -32602 is no longer considered proof of accessible
key RPC: argument parsing failures can occur without reaching the policy gate.
The reported 1040 decoding response is also not a valid result for the new
well-formed lookup.

## Exact binary observation

[Machine-readable receipt](evidence/rpc-policy-v1.1.0-20260914.json)

- Node: `3.0.0-dev-be8920f47d2`, corresponding to the v1.1.0 testnet build.
- Binary SHA-256: `1643b8a4416efcef8fe3fc7d56a562dc2ab93b7a3446ff531c1d302680c2ff5a`.
- Disposable `local_testnet` Full node, no configured peers, loopback listeners,
  no offchain worker, no key RPC writes. Temporary state was held in tmpfs.
- Safe: both lookups return explicit denial -32601; corrected CLI exits 0.
- Unsafe: the old empty tuple returns 1040, `Session keys are not encoded
  correctly`; the new lookup returns `false`; corrected CLI exits 2.
- Restored Safe: explicit denial again; corrected CLI exits 0.
- All owned node processes stopped and temporary state removed.

Reproduce against a separately verified binary with:

```bash
python3 test/rpc_policy_live.py --binary /path/to/verified/roko-node
```

The runner uses only its disposable local chain; its evidence is not a receipt
for the operator's installed service or live testnet enrollment. The initial
attempt using the unsupported chain alias `local` exited before RPC startup;
source inspection identified the supported `local_testnet` alias used above.

## Guarded helper contract

The full smoke suite includes `test/rpc_policy_contract.py`, which exercises
the actual CLI and guarded shell helper over a real loopback HTTP listener.
Service control and generation are fixtures. Coverage includes both denial
codes, true/false lookup results, the historical decoding/argument errors,
proxy/missing-method errors, malformed results, unknown failures, restart and
generation failures, TERM interruption, and failed restoration proof. Unknown
policy prevents generation; failed restoration proof stops the service.

The helper restores the original policy backup bytes and metadata, including
an accepted CRLF policy file, then verifies Safe through RPC. It retains the
backup. Existing loopback/no-forwarding, ownership, non-authoring, and key
custody gates remain required.

## Real guarded-service qualification

The [guarded-service qualification](guarded-enrollment-qualification.md) now
covers successful generation and real restart, interruption and RPC failures
with both v1.1.0 and nightly 086baf26 nodes executing the exact public runtime
286 in a disposable genesis. Source and cleanup receipts are retained.

## Delivery limits

This does not qualify owner-signed enrollment, Agora package import, the
reporter's custom service/PHC configuration, another architecture or a node
build outside the recorded matrix. Signed release publication remains a
separate gate; source qualification alone is not a first-fixed-release claim.
