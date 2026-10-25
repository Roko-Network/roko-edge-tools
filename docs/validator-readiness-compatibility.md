# Validator readiness compatibility — tooling 1.4.9

[Tooling 1.4.9](https://github.com/Roko-Network/roko-edge-tools/releases/tag/v1.4.9)
was published as a signed GitHub prerelease on **2026-10-25 UTC**. Its annotated
tag targets source `53c42a826c7c256790d64d88930f31e1e39384ce`. All ten public
GitHub assets matched the frozen release inventory on anonymous download;
metadata, checksum-manifest and tag signatures verified against release key
`62297562B1C7053088F405DB0117DAAA677A5BF2`.

The canonical versioned directory and CURRENT were activated on the same UTC
date; all ten files at each location matched the signed release bytes on
anonymous download. Use the [versioned 1.4.9 installer](https://downloads.roko.network/validator-tools/1.4.9/install-roko-validator-enroll.sh)
and the [signed-manifest-first installation sequence](../README.md#signed-validator-enrollment-tools).
The [CURRENT alias](https://downloads.roko.network/validator-tools/current/roko-validator-enroll-1.4.9.metadata.json)
serves the same release; versioned URLs keep an installation pinned.

## What is qualified

The actual signed, freshly installed 1.4.9 bundle passed the bounded disposable
Linux amd64 native fixture with node build
`fba4e76cfeb062bcba0cc2c2fd16f9d9b23c275b` (`nightly-fba4e76c-20261015`) and
runtime spec 290. Native binary SHA256:
`adfd8009807d340e389a8308579da84ac62c36e257c3b9122427a49fb85b6206`.
Runtime Wasm SHA256:
`c90d0f20950475f295d4c84d7a5b6d896d71574e7ce9e74c241ea3d1013b5147`.

The installed command exported all ten expanded readiness fields through the
real isolated candidate's Safe RPC endpoint. The candidate remained
`NON_AUTHORING_NODE`, with `validatorRoleConfigured: false` and
`readyToAuthor: false`. Generation, seven-key reuse, Safe restoration, three
failure cases and six Agora rejection cases passed. Owned fixture processes
and temporary state were cleaned up; production service identity was preserved.

Synthetic tests separately cover `ELIGIBLE_WITH_WARNINGS` and
`TIME_ENFORCEMENT_DISABLED`, unchanged report export, legacy report shapes and
rejection of unknown, partial or inconsistent fields. A warning is not strict
timing qualification, and disabled enforcement is not readiness to author.

This qualifies the disposable fixture and the installed expanded-report parser.
It does not establish live enrollment, real browser-wallet signing, election,
rewards, strict timing or UTC accuracy. ARM enrollment and other native-build
or runtime tuples require their own executions. Follow the
[local node-wallet primary path](validator-node-wallet.md) and respect all
existing readiness and admission gates.

## Historical 1.4.8 limitation

The immutable signed 1.4.8 archive contains the older parser. It rejects the
expanded report even when the lifecycle state itself is familiar.
Readiness-dependent operations, including `--save-readiness` and transition
fallbacks that capture readiness, can therefore fail on this node build. This
does not establish that every local node-wallet operation fails.

The 1.4.8 profile's runtime-290 entry records its qualification scope; it does
not establish acceptance of every raw RPC payload. Runtime spec alone cannot
identify a native node's RPC contract. Earlier install examples and receipts
remain historical evidence for their exact versions. Neither the 1.4.8 archive
nor its tag was replaced to deliver 1.4.9. Do not bypass readiness checks or
enable unsafe RPC to work around a parser failure.

## Source and release references

- [Readiness contract compatibility issue #59](https://github.com/Roko-Network/roko-edge-tools/issues/59)
- [Signed 1.4.9 checksum manifest](https://downloads.roko.network/validator-tools/1.4.9/SHA256SUMS)
- [Signed 1.4.9 metadata](https://downloads.roko.network/validator-tools/1.4.9/roko-validator-enroll-1.4.9.metadata.json)
- [Historical 1.4.8 signed manifest](https://downloads.roko.network/validator-tools/1.4.8/SHA256SUMS)
- [Historical 1.4.8 metadata](https://downloads.roko.network/validator-tools/1.4.8/roko-validator-enroll-1.4.8.metadata.json)
- [Pinned native readiness fields](https://github.com/Roko-Network/roko_network/blob/fba4e76cfeb062bcba0cc2c2fd16f9d9b23c275b/node/rpc/src/temporal.rs#L631)
