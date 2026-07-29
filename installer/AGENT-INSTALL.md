# ROKO node agent handoff

Use this contract when an AI agent is installing a ROKO testnet node for an
operator. The bundled launcher is the execution authority. The
`setup.aiwg.io/v1` manifests are the machine-readable plan.

## Operator choices

Collect all of these choices before running an installation step:

- node name;
- role: `full`, `archive`, `observer`, or `validator-candidate`;
- runtime: `native` or `docker`;
- clock path: `chrony` or `timebeat`;
- synchronization timeout; and
- readiness-report path.

For Timebeat, also ask the operator to place the vendor package, per-node
licence, and reviewed configuration on the target host. Ask only for their
local file paths. Never request, display, copy, summarize, or transmit the
contents of a licence, key, token, or proprietary configuration.

## Required execution protocol

1. Clone or update the public
   [`Roko-Network/roko-edge-tools`](https://github.com/Roko-Network/roko-edge-tools)
   repository.
2. Read this file, `installer/README.md`, and the selected manifest:
   `installer/setup.user.manifest.yaml` for Chrony or
   `installer/setup.timebeat.manifest.yaml` for Timebeat.
3. Inspect the referenced scripts. Do not replace them with improvised
   installation commands.
4. Collect every required operator choice before executing a step.
5. Run the selected launcher command with `--dry-run`.
6. Show the resolved plan and wait for explicit operator approval.
7. Run the same launcher command without `--dry-run`.
8. Report success only after the readiness gate proves the expected genesis,
   one or more peers, `isSyncing: false`, stable peer identity, and advancing
   finality. Give the operator the readiness-report path.

Chrony:

```bash
./bin/roko-guided-install --time-stack chrony --dry-run
./bin/roko-guided-install --time-stack chrony
```

Timebeat:

```bash
./bin/roko-guided-install --time-stack timebeat --dry-run
./bin/roko-guided-install --time-stack timebeat
```

AIWG is optional on the target. If its `setup-run` and `setup-validate`
commands are available, they may be used to validate and inspect the
manifests. The bundled launcher remains the compatible public execution path.

## Hard safety boundaries

Do not:

- expose RPC or open firewall ports;
- reset or delete chain data;
- create, rotate, reveal, or export wallet, session, libp2p, PTP², licence, or
  signing-key material;
- enroll a validator, bond funds, alter the authority set, or enable authoring;
- run an unreviewed recovery step; or
- claim completion because a service is merely active.

Stop and ask the operator before any action outside the printed dry-run plan.
A `validator-candidate` installation must finish as a fully synchronized,
non-authoring peer. Validator activation is a separate reviewed process.

## Completion response

Return a concise report containing:

- selected role, runtime, and clock owner;
- installed node revision and verified testnet genesis;
- peer count, synchronization state, and finality result;
- readiness-report path;
- any skipped or failed gate; and
- the next reviewed action, if the role is `validator-candidate`.

Do not include secrets, licence values, private configuration contents, or
private keys in the response.
