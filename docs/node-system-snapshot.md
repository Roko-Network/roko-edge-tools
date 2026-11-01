# Node system snapshot

`bin/roko-node-snapshot` writes one JSON file that describes the host a ROKO
node runs on: hardware, operating system, storage, network capability, node
installation and configuration, clock discipline, and a short utilization
sample. Operators share the file with the ROKO team for troubleshooting, and
the team aggregates snapshots for capacity planning and hardware guidance.

It is read-only, uses only the Python 3.10+ standard library, and does not
need root. It does not read keys, keystores, wallets, environment variables,
logs or configuration file contents.

## Run it

```bash
git clone https://github.com/Roko-Network/roko-edge-tools.git
cd roko-edge-tools
./bin/roko-node-snapshot
```

The command samples utilization for five seconds, prints a summary, and writes
`roko-node-snapshot-<UTC time>.json` with mode `0600`. It never overwrites an
existing file. Review the JSON before you send it.

Useful options:

| Option | Effect |
|---|---|
| `--label site-a-01` | Add your own label so you can tell snapshots apart |
| `--sample-seconds 30` | Longer utilization window (0-60; `0` skips sampling) |
| `--json` | Print the JSON to stdout instead of writing a file |
| `--no-rpc` | Do not query the node's JSON-RPC |
| `--no-du` | Skip measuring the chain database size on very slow disks |
| `--service`, `--base-path`, `--binary` | Override auto-detection |
| `--include-identity` | Also record the hostname and node peer ID |

The service unit, binary path and data directory are detected from the
running `roko-node` process. Without a process, the defaults are the guided
installer's: `roko-node.service`, `/usr/local/bin/roko-node` and
`/var/lib/roko`. For Docker installations, run the tool on the host, not
inside the container.

### Privileges

Run it as your normal user first. Some facts are only readable by the node's
service user or root, and the snapshot lists each one under `collectionGaps`
instead of guessing:

- chain database size (the data directory is usually private to the node user);
- the node binary checksum when the install directory is restricted;
- the node process's open file count.

To include them, run it as the node's service user, for example
`sudo -u roko ./bin/roko-node-snapshot --output /tmp/snapshot.json`. Root also
works but is not required.

## What is collected

| Section | Contents |
|---|---|
| `host` | OS release, kernel, architecture, virtualization, platform model, CPU model/topology/features, governor, memory and swap totals, cgroup limits |
| `storage` | Block devices (size, type, rotational, transport, model), the data filesystem (type, allow-listed mount options, capacity, free space, backing disk, scheduler), chain directory names and sizes |
| `network` | Physical, wireless and bond interfaces (name, link speed, MTU, error counters); counts of other interface kinds; whether ROKO ports listen on loopback, all interfaces or a specific address; established P2P connections |
| `roko` | Deployment type, service state, restarts, memory/CPU accounting, process memory/threads/limits, binary version and SHA-256, and the node's command-line flags |
| `time` | Synchronization state, active time services, Chrony stratum/offsets/leap status and source counts, PTP hardware clock names |
| `node` | Safe RPC only: version, chain, roles, peers, sync and finalized height, runtime spec, mesh peer count and quality |
| `utilization` | Load average, pressure-stall averages, CPU busy/iowait/steal, data-disk IOPS/throughput/busy, NIC throughput, node CPU use |
| `checks` | Results against requirements already documented in this repository; each entry names its source file |

## What is never collected

- Private keys, session keys, node keys, wallets, seeds or mnemonics.
- IP addresses, MAC addresses, serial numbers, usernames or home-directory names.
- The hostname, node name or peer ID, unless you pass `--include-identity`.
- Values of node flags outside a fixed allow-list. `--name`, `--node-key-file`,
  `--bootnodes`, `--reserved-nodes` and every other non-allow-listed flag is
  recorded by name with the value `[redacted]`.
- Chrony source names or addresses.
- Process environments, logs, service file contents or configuration file contents.

Before writing, the tool scans its own output for key-shaped values, IPv4 and
MAC addresses, bearer tokens, PEM private keys, mnemonic-like word runs and
prohibited field names. If anything matches, it writes nothing and exits `3`.

Node RPC is only queried on a loopback address unless you pass
`--allow-remote-rpc`. The snapshot records only whether the endpoint was
loopback or remote, never the URL.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Snapshot written or printed |
| `2` | Invalid option, non-loopback RPC without opt-in, or output file already exists/unwritable |
| `3` | Refused: the privacy scan matched; nothing was written |

## Contract

The output follows `roko.node-system-snapshot.v1`, defined in
[`contracts/node-system-snapshot-v1.schema.json`](../contracts/node-system-snapshot-v1.schema.json).
Fields that cannot be read are `null`, and each such gap appears in
`collectionGaps` with its reason. Consumers should treat `null` as "not
observed", never as zero or false.

The `checks` section covers only requirements already written down here: the
supported architectures and distributions and the data volume minimums (200 GiB,
or 1000 GiB for an archive node) from `installer/scripts/preflight.sh`; Safe RPC
methods and loopback-only RPC from the README; and at least two selectable
clock sources from the time-authority verification guide. It does not yet
grade CPU, memory or network sizing; those recommendations will come from
aggregated snapshots.
