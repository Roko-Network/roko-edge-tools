# Private enrollment qualification preparation

The signed 1.4.5 release and its published spec285–287 support remain unchanged.
The [runtime 290 candidate fixture](evidence/guarded-fba4-runtime290-candidate-20261015.json)
passed with the exact FBA AMD64 node and production mainnet Wasm while using
unchanged signed 1.4.5 tools outside their published compatibility. Both generated
and reused packages passed the actual Agora module, all six rejection cases and
all three restoration faults. The seven existing keys were preserved and owned
cleanup completed. Production identity and headroom were sampled during the run;
production finality samples were postflight only. No browser, live readiness,
physical-time or ARM enrollment qualification is established.

Source version 1.4.6 is **unpublished preparation**. Its profile binds the
network's live runtime, spec 286, and the node build the managed fleet runs:
AMD64 release `nightly-f490bcd1-20261014`, source
`f490bcd12df8af67e9bd009482fbc1954199d7f1`, node `3.0.0-dev-f490bcd12df`,
SHA256 `b0ddc0fdae81ce09b1f6c9b18eee61f86ab6d35ec53b825bcfcc77acf3e66fdc`.
The runtime 290 candidate is not active on the network and is no longer the
release target. The ARM64 member of the same release (SHA256
`272d20659a047a530280a4fa9018cf16f450ec3fffecb3b669af336856a74fc2`) has no
enrollment fixture and is not in the profile. Run the guarded fixture with the
exact runtime 286 Wasm (code SHA256
`2b2c062997dbe9575305a263656a9fb46dc794108944907eec152a5bee4945d3`), then build
and sign 1.4.6, install it in a new isolated prefix, and repeat the actual
fixture and checker in delivery mode with `--runtime-spec 286`. Publication
requires that fresh assessment to report `deliveryBinding:true`. Historical
receipts, 1.4.5 release fixtures and their published range remain immutable.

The runner now requires an owned systemd campaign. Use
`test/run_guarded_enrollment_qualification.py` with the independently reviewed
SHA256 of `test/guarded_enrollment_live.py`, a new receipt path, and the existing
harness options after `--`. The wrapper runs the operator's harness service
under an owned flat-name slice with MemoryMax12GiB, CPUQuota400%, TasksMax1024,
RuntimeMax30minutes and TERM cleanup grace90seconds. Authority child processes
inherit this service's cgroup; the candidate service joins the same aggregate
slice with MemoryMax2GiB. The harness verifies the actual manager properties,
its own PID/cgroup and candidate membership before generation. The wrapper
checks the production service identity and removes only its exact owned units
and slice file. No address-space limit is used.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 test/run_guarded_enrollment_qualification.py \
  --expected-harness-sha256 REVIEWED_HARNESS_SHA \
  --production-service roko-titan.service --receipt NEW_NATIVE_RECEIPT -- \
  --binary FINAL_NATIVE_BINARY --expected-sha256 FINAL_BINARY_SHA \
  --runtime-wasm FINAL_PRODUCTION_WASM --expected-runtime-sha256 FINAL_WASM_SHA \
  --expected-runtime-spec 286 --tool-bin VERIFIED_INSTALLED_LINKS \
  --agora-module FINAL_EXACT_AGORA_MODULE --agora-sha256 FINAL_MODULE_SHA
```

During the helper's existing reuse window, the runner independently asks
`author_hasSessionKeys` about the previously generated public tuple. It never
opens another Unsafe window. If restoration closes the observation opportunity,
the receipt explicitly records helper attestation instead: the authenticated
installed generator itself requires an exact `True` response before restoring
Safe. An unsuccessful independent custody response fails the fixture. Secret
key files remain comparison-only in memory; no contents or their hashes enter
receipts.

`scripts/verify-enrollment-receipt.py` verifies pinned-authority signatures on
both tools and node metadata/checksums in a disposable public-only keyring.
The exact authority fingerprint is `62297562B1C7053088F405DB0117DAAA677A5BF2`.
It binds every resolved installed command and packaged library to the signed
archive, verifies immutable 1.4.5 identity, native ELF architecture, reviewed
runner/wrapper hashes, observed network tuple, all six explicitly-True Agora
negative cases, all three fault cases, seven-key reuse, exact Safe restoration
and complete owned cleanup. It creates a new private assessment; it never
changes a release profile or manufactures fixture results.

`--mode candidate` is explicitly spec290 with unchanged signed 1.4.5 outside
published support. Its result has `deliveryBinding:false`. `--mode delivery`
requires authenticated published compatibility and an exact qualified-build
entry matching full source revision, binary SHA, runtime spec, architecture and
display version. A new release must support precisely its tested spec. The
unpublished 1.4.6 profile binds exactly the live spec 286; a fresh fixture
with the signed 1.4.6 tools is still required.

Node inputs can be directly covered by the signature-verified checksum list.
Alternatively, root may provide a separately signed private operator attestation
with schema `roko.enrollment-artifact-attestation.v1` and issuer
`roko-operator-private-qualification`. It binds actual source revision/tree,
architecture/image, upstream release metadata/checksum digests and exactly three
roles (`binary`, `runtimeWasm`, `agoraModule`), each with actual path/SHA256.
Derivations are explicitly `signed-native-archive`,
`independently-reproduced-production`, and `exact-source-export`. Binary role
also names the actual native archive SHA and `roko-node` member; the checker
independently hashes that member and compares the exported binary. This is an
operator-derived attestation, not a claim that upstream metadata publishes all
three raw roles. No new public asset format is required.

Root supplies final artifacts, signed provenance and execution capacity. Use
`--help` for checker inputs, including node detached signatures, optional
private attestation/archive, signed tools release directory, installed links,
reviewed harness/wrapper paths and hashes, architecture/spec and new output.
The legacy private checker and old evidence remain separate and unchanged.

The offline regression suite includes immutable public1.4.5 signatures/archive
under `test/fixtures/validator-enroll-1.4.5`. Source:
`https://github.com/Roko-Network/roko-edge-tools/releases/tag/v1.4.5`.
Archive SHA256 is
`b1c371618a91369bd1e4537485dbce165d9d58cd5bb1e1b2b38bcca45e29b162`.
These are historical signature-regression inputs, not new qualification receipts.
Pure assessment tests use explicitly synthetic receipt data; no services,
native nodes, wallet transactions or public RPC are exercised by ordinary smoke.

The root-controlled fixture must use a fresh isolated signed-tools installation,
not an existing shared installation. Authenticate the install before execution
with the checker's `authenticated_tools` preflight, then authenticate it again
when assessing the final receipt. All four commands must be signed archive
members, and the package's regular files must exactly match that archive; extra
modules, file or directory links, special files and preexisting `__pycache__`
are rejected. Nothing is deleted or silently excluded to make a package pass.
Set `PYTHONDONTWRITEBYTECODE=1` on install/qualification/checker invocations.
The campaign service inherits this setting, tool subprocesses receive it, and
privileged helper calls set it inside sudo's root environment. The version
probe also receives it. This prevents newly generated unsigned bytecode.

Both real argument parsers disable abbreviations. The wrapper rejects forwarded
owned options and additional `--` delimiters and parses the full harness grammar
before any service operation. Every package network field must match the
independently observed six-field tuple, including genesis and runtime version.
The actual Agora contract emits an explicit `true` for a negative only after
asserting its exact rejection code; `rejectionCodes` retains those codes
separately. Offline smoke executes this emitter against the exact retained
Agora module export in `test/fixtures/agora-validator`; `SOURCE.json` pins its
source revision and SHA256. Its generated fixture and checker assessment remain
synthetic offline regressions, not native qualification receipts.

The wrapper requires explicit `--production-service` before the harness delimiter.
Supply the host's actual canonical managed ROKO unit, such as
`roko-titan.service` for the reviewed Titan fixture; there is no assumed service
alias. Before any fixture install or service mutation, the named unit must report
that exact `Id`, `LoadState=loaded`, `ActiveState=active`, positive `MainPID` and
an absolute nonempty `ControlGroup` outside the owned campaign slice. Unknown,
inactive and aliased units are refused. The wrapper reads the same fields after
owned cleanup and records both snapshots in `productionService`; any identity
change or failed observation makes the receipt fail. The private checker requires
independent `--expected-production-service` for both candidate and delivery modes,
validates both active snapshots and isolation, and requires identical before/after
state. A preservation boolean alone is insufficient. These observations protect
the existing service identity; they do not establish runtime activation or live
network readiness. Root must review the updated wrapper/checker hashes before
execution. The harness bytes remain unchanged.
