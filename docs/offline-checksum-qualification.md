# Offline checksum qualification — 2026-09-14

Issue: https://github.com/Roko-Network/roko-edge-tools/issues/13

The published [v1.1.0 offline sidecar](https://github.com/Roko-Network/roko-edge-tools/releases/download/v1.1.0/roko-validator-enroll-offline-1.1.0.tar.gz.sha256)
contains an absolute build-machine path. Downloading it and the matching
[archive](https://github.com/Roko-Network/roko-edge-tools/releases/download/v1.1.0/roko-validator-enroll-offline-1.1.0.tar.gz)
into an unrelated directory reproduces `sha256sum --check --strict` failing
with `No such file or directory` for the original build path.

The downloaded archive's SHA-256 is
`2c9ba2c590fab7584ca1adac64c26c31434baf1a3841d67c3f7e3971a2af515e`,
which matches the sidecar digest. Its extracted `SHA256SUMS.asc` and metadata
signature verify against the repository-pinned release fingerprint
`62297562B1C7053088F405DB0117DAAA677A5BF2`; all four entries in the authenticated
`SHA256SUMS` pass strict verification. No downloaded installer was executed.
This confirms a nonportable sidecar, without evidence of changed payload bytes.

The same builder defect exists in main revision
`ae0d969` (tool version 1.3.0). The correction computes the checksum from the
output directory using the archive basename. The release regression moves the
archive and sidecar into an unrelated directory containing spaces, leaving the
original archive absent, and runs strict verification there. It also requires
verification to fail after modifying the relocated archive. The regression
failed before the builder change and passes afterwards. The complete
`test/smoke.sh` suite passes, including authenticated installer and tampering
checks with an isolated fixture signing key.

This is source qualification, not a newly signed production release. The
historical GitHub assets remain unchanged; no first fixed published version is
claimed. Exact node/tool compatibility, guarded-window qualification (#14),
existing-install preflight, and wallet/finalized enrollment acceptance remain
separate unfinished requirements of #13.
