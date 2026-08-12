# ROKO node agent handoff

Use this contract when an AI agent is installing a ROKO testnet node for an
operator. Begin at [`../docs/time-authority/README.md`](../docs/time-authority/README.md),
read its `docset.yaml`, and follow the route for the operator's role. The
metadata and Pagenbar links work with or without AIWG. The bundled launcher is
the execution authority and the `setup.aiwg.io/v1` manifests are the
machine-readable plan.

## Operator choices

Collect all of these choices before running an installation step:

- node name;
- role: `full`, `archive`, `observer`, or `validator-candidate`;
- runtime: `native` or `docker`;
- clock path: `chrony` or `timebeat`;
- synchronization timeout; and
- readiness-report path.

Explain the resulting connectivity before approval:

- every role joins the ROKO blockchain P2P network and runs the ROKO time
  protocol;
- `observer` adds authenticated ROKO PTP² advertisement with a dedicated
  local key;
- `timebeat` joins a separate operator-configured licensed PTP² timing mesh;
  and
- selecting `observer` with `timebeat` enables both PTP² layers alongside
  ROKO chain P2P.

For Timebeat, ask the operator to place the vendor package, per-node licence,
and reviewed PTP Squared configuration on the target host. Ask only for local
file paths. Never request, display, copy, summarize, or transmit licence, key,
token, or private topology contents.

## Required execution protocol

1. Clone or update the public
   [`Roko-Network/roko-edge-tools`](https://github.com/Roko-Network/roko-edge-tools)
   repository.
2. Read `docs/time-authority/README.md`, `docs/time-authority/docset.yaml`, the
   pages selected by that route, this file, `installer/README.md`, and the selected manifest:
   `installer/setup.user.manifest.yaml` for Chrony or
   `installer/setup.timebeat.manifest.yaml` for Timebeat.
3. Inspect the referenced scripts. Do not replace them with improvised
   installation commands.
4. Collect every required operator choice before executing a step.
5. Run the selected launcher command with `--dry-run`.
6. Show the resolved plan and wait for explicit operator approval.
7. Run the same launcher command without `--dry-run`.
8. Report success only after the readiness gate proves the expected genesis,
   one or more ROKO peers, an available ROKO time-mesh RPC, a non-authoring
   role, `isSyncing: false`, stable peer identity, and advancing finality. Give
   the operator the readiness-report path.

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
- sign for the user, ask the user to paste a seed/private key, alter the
  authority set, or enable authoring before active-session verification;
- run an unreviewed recovery step; or
- claim completion because a service is merely active.

The public workflow must not reveal or depend on internal ROKO timing systems.
Use the verified 2.3.5 package and an operator-reviewed public or self-operated
PTP Squared profile. Chrony must select at least two independent bootstrap
sources, and the ROKO node's minimum time-source requirement must remain two.

Stop and ask the operator before any action outside the printed dry-run plan.
A `validator-candidate` installation must first finish as a fully synchronized,
non-authoring peer. The agent may then explain wallet setup, open the public
claim/staking pages, read public balances and receipts, and guide the user
through the manifest's interactive onboarding prompts. The user performs every
wallet confirmation. The current testnet target is a 50-pwROKO self-bond plus
liquid ROKO for fees. The live runtime does not expose EVM staking precompile
`0x0700`; require a native staking ledger rather than an EVM success receipt as
bond proof. Do not confuse lock, bond, session-key registration,
validate intent, candidacy, queued selection, and active-session membership.

## Completion response

Return a concise report containing:

- selected role, runtime, and clock owner;
- installed node revision and verified testnet genesis;
- peer count, synchronization state, and finality result;
- ROKO PTP² mode and whether Timebeat PTP² was selected;
- readiness-report path;
- any skipped or failed gate; and
- the next reviewed action, if the role is `validator-candidate`.

Do not include secrets, licence values, private configuration contents, or
private keys in the response.
