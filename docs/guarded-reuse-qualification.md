# Guarded existing-key reuse qualification

The new source option `roko-session-key-window --reuse-session-keys` opens the
same bounded RPC window as generation, invokes the CLI with `--session-keys`,
and restores the exact prior Safe configuration. It never requests rotation or
falls back to generation if custody fails. This option first appears in tooling 1.4.1; it is not in signed 1.4.0.

On 2026-09-14, the native/systemd harness passed on Linux amd64 node source
`086baf26c0e0db666526b8f649269facd1c37da7` using public runtime 286 code in an
isolated development genesis. The [receipt](evidence/guarded-reuse-nightly086-20260914.json)
binds the binary, runtime and harness digests. It proves:

- Real generation followed by a fresh package for the identical public tuple.
- All seven existing key files unchanged, compared in memory without retaining
  private bytes or secret-derived hashes in the receipt.
- Exact prior Safe policy restoration and live Safe RPC proof after reuse.
- Restart failure, interruption and RPC loss still restore Safe, preserve keys
  and do not create a package. Those fault injections use generation mode;
  reuse-specific error sequencing is covered by the contract tests.
- Temporary service, processes and tmpfs state removed after the test.

Eleven CLI/helper contract cases and the full smoke suite passed. These include
malformed reuse input failing before restart and custody failure returning its
error without a generation fallback. Contract service/generation behavior is
stubbed; the native receipt above supplies the real key-preservation evidence.

An attempted follow-on Agora-module import check ran after the fixture's
cleanup and failed because the public package no longer existed. It provides
no importer acceptance evidence. Integrate that check into the fixture lifetime
before claiming compatibility with Agora; browser signing and owner finality
remain separate checks. This run does not qualify PHC derivatives, production
clock enforcement, public temporal transport or an operator's registration.

## Actual Agora contract

The follow-up run moved the importer check inside the fixture lifetime.
[Receipt](evidence/guarded-reuse-agora086-20260914.json) records acceptance of
both generated and reused packages by the actual standalone Agora module from
core source `086baf26c0e0db666526b8f649269facd1c37da7` (module SHA-256
`d41eb32e117661ca2a6e535c8f0001847b2c31cdba7695f742493ea81f19b79c`).
It ran in Node, not a browser. The harness reads expected genesis, runtime and
metadata independently from local RPC before invoking the module. Both
packages reject wrong genesis, runtime and metadata, expiry, digest tampering
and replay with the expected reason codes. The full importable packages are
removed with the fixture; receipts retain only public verification facts.

Reproduce by exporting the pinned module from the core repository and adding
`--agora-module PATH --agora-sha256 d41eb32e117661ca2a6e535c8f0001847b2c31cdba7695f742493ea81f19b79c`
to the native harness arguments. The Node runner checks the module digest
before importing its exact bytes. A missing or incorrect module fails rather
than substituting a mock. Browser connection, live application deployment and
owner-signed finalized enrollment remain unverified by this test.

The same complete harness also passed on the historical amd64 v1.1.0 node
`be8920f47d282da73297c17875791c4e3d444625` with runtime 286:
[receipt](evidence/guarded-reuse-agora-v110-20260914.json). Both generated and
reused packages passed the pinned Agora validator and all six rejection cases;
seven unchanged key files, exact Safe policy and all service-fault recoveries
were verified. The temporary service and state were removed.
