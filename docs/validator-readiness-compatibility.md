# Validator readiness compatibility — unreleased source fix

The source parser now accepts the additional readiness fields emitted by node
build `fba4e76cfeb062bcba0cc2c2fd16f9d9b23c275b` (runtime spec 290), including
`ELIGIBLE_WITH_WARNINGS` and `TIME_ENFORCEMENT_DISABLED`. It preserves the raw
report and validates the timing profile, participation flags, enforcement mode,
quality bounds and diagnostic integer ranges. Older report shapes remain
supported; unknown fields, partial field groups and inconsistent evidence fail
closed. A warning is not strict timing qualification, and disabled enforcement
is not readiness to author.

**This is a source change, not a new qualified release.** On 2026-10-24, the
signed, versioned tooling 1.4.8 archive still contained the older parser. It
rejects the expanded report even when the lifecycle state itself is familiar.
Readiness-dependent operations, including `--save-readiness` and transition
fallbacks that capture readiness, can therefore fail on this node build. This
does not establish that every local node-wallet operation fails.

The 1.4.8 compatibility profile's runtime-290 entry describes its recorded
qualification scope; it does not establish acceptance of every raw RPC payload.
Runtime spec alone cannot identify a native node's RPC contract. Earlier install
examples and qualification records remain historical and must not be read as
current expanded-contract qualification.

A new signed release, with an updated artifact identity and actual bounded
qualification against the intended native node build, is required before this
fix can be advertised as an installed release capability. Do not replace or
relabel the immutable 1.4.8 archive, bypass readiness checks, or enable unsafe
RPC to work around a parser failure. Follow the [local node-wallet primary
path](validator-node-wallet.md) for enrollment guidance and respect all existing
readiness and admission gates.

The synthetic tests exercise old and expanded reports, policy rejection and
unchanged evidence export with a fake Safe RPC client. They do not perform
wallet operations, submit transactions or qualify a live enrollment.

## Source and release references

- [Readiness contract compatibility issue #59](https://github.com/Roko-Network/roko-edge-tools/issues/59)

- [Versioned 1.4.8 signed manifest](https://downloads.roko.network/validator-tools/1.4.8/SHA256SUMS)
- [Versioned 1.4.8 metadata](https://downloads.roko.network/validator-tools/1.4.8/roko-validator-enroll-1.4.8.metadata.json)
- [Pinned native readiness fields](https://github.com/Roko-Network/roko_network/blob/fba4e76cfeb062bcba0cc2c2fd16f9d9b23c275b/node/rpc/src/temporal.rs#L631)
