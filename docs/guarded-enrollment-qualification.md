# Guarded enrollment qualification — 2026-09-14

The real `roko-session-key-window` helper and `roko-validator-enroll` CLI passed
generation and recovery checks against a temporary systemd-managed Full node.
Three separate development authorities supplied advancing finalized blocks.
All node listeners bound loopback; peer discovery, telemetry and public peers
were disabled. Only predictable development authority identities and newly
generated disposable session keys were used. State and policy backups lived
in tmpfs and were removed after the owned service and processes stopped.

## Qualified node builds

| Node release | Display version | Linux amd64 binary SHA-256 | Receipt |
| --- | --- | --- | --- |
| v1.1.0 | `3.0.0-dev-be8920f47d2` | `1643b8a4416efcef8fe3fc7d56a562dc2ab93b7a3446ff531c1d302680c2ff5a` | [v1.1.0](evidence/guarded-v110-runtime286.json) |
| nightly-086baf26-20260913 | `3.0.0-dev-086baf26c0e` | `8b2a403b2fe047882098d232690a6eda3fe82133baa01f6a0fb3924ed9d5bdc6` | [nightly](evidence/guarded-nightly086-runtime286.json) |

The nightly archive was retrieved from the immutable release-origin directory.
Its SHA-256 is `5b263d7c94bfbf52671d4bf867d3d934cbafe054281b2faa268029cb90dd6d84`,
matching that release's checksum manifest. Testing v1.1.0 does not recommend
downgrading a newer installed node. Display versions, release identifiers,
source revisions and tooling versions are distinct facts.

Both tests used runtime spec **286**, code SHA-256
`2b2c062997dbe9575305a263656a9fb46dc794108944907eec152a5bee4945d3`,
read from the public chain at a pinned finalized hash in the
[runtime-source receipt](evidence/runtime286-source.json). Only this public
runtime code was transplanted into development genesis state. The genesis
hashes remain distinct from the live chain and no transaction was sent there.
The three development authorities used log-only timing to supply test finality;
this is enrollment qualification, not strict timing or relay qualification.

## Results on each build

- The candidate reported Full role, at least two peers, synchronized state and
  advancing finality before enrollment.
- Real service restart opened the bounded Unsafe window, generated a public
  package and proved local session-key custody. The helper exited 0, restored
  exact Safe policy bytes, restarted the service and verified explicit denial.
- Injected Unsafe restart failure exited 1 and restored verified Safe.
- TERM interruption while Unsafe was accessible exited 143 and restored
  verified Safe.
- Stopping the real RPC service during the generation observation caused
  failure exit 1 and restoration to verified Safe.
- All three failures wrote no new package and preserved the existing seven
  key filenames. The nightly run additionally compared their private file
  bytes in memory and recorded only the equality result, never values/hashes.
- Final readback confirmed every owned process stopped, temporary service
  removed and tmpfs state removed. Host reconciliation is recorded on Grissom
  DATAGERRY object 2 and in the paired itops qualification report.

The runner is [test/guarded_enrollment_live.py](../test/guarded_enrollment_live.py).
It requires exact binary/runtime digests, explicit paths, a new receipt path,
local systemd/sudo capability and synchronized host time. It is opt-in and is
not part of ordinary smoke tests. Its current source hash is retained by the
nightly receipt.

## Earlier attempts retained

1. [Attempt 1](evidence/guarded-v110-attempt01.json): exited before RPC startup;
   cleanup passed, but the original harness did not retain startup diagnostics.
2. [Attempt 2](evidence/guarded-v110-attempt02.json): reproduced the failure and
   identified the validator's intentional missing-network-key refusal. The
   fixture was corrected to supply predictable development keys through files.
3. [Attempt 3](evidence/guarded-v110-attempt03.json): deliberately interrupted
   after detecting a reserved-only fixture topology that rejected unlisted
   incoming peers. Cleanup passed. Later runs allow bounded inbound loopback
   peers and disable non-reserved outbound peers; no public network is used.
4. [Attempt 4](evidence/guarded-v110-runtime282-attempt04.json): real generation
   succeeded but the built-in development runtime was 282, outside the
   advertised 285–287 range. It was not accepted as runtime-286 qualification.

## Scope limits

These results do not authorize changing an operator's custom PHC service,
rotating their existing tuple, or submitting wallet transactions. Existing
service compatibility and key reuse need their own preflight. Agora import,
owner-signed enrollment and finalized election are separate acceptance gates.
These short service-restart tests do not establish recovery from #18's
14-hour catch-up failure or #12's public relay quorum problem. Only Linux amd64
and the two exact builds above were qualified here.
