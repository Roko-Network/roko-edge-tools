# Guarded existing-key reuse qualification

The new source option `roko-session-key-window --reuse-session-keys` opens the
same bounded RPC window as generation, invokes the CLI with `--session-keys`,
and restores the exact prior Safe configuration. It never requests rotation or
falls back to generation if custody fails. This option is not in signed 1.4.0;
a new signed release is required before operator deployment.

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
