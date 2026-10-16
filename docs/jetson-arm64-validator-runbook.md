# ROKO validator on a Jetson (arm64): operator runbook

## Purpose

This runbook takes an already-synced ROKO testnet node on an NVIDIA Jetson to
an enrolled validator candidate using only published, checksum- or
signature-verified artifacts. Nothing is built from source.

It covers eight steps:

1. Preflight the Jetson and record the current unit.
2. Pin the node to the release the network runs.
3. Install the signed enrollment tools 1.4.7.
4. Get the signed service installer and the authority peer list.
5. Install the supported validator-candidate systemd unit.
6. Generate session keys inside the guarded window.
7. Sign the four wallet transactions on your separate wallet machine.
8. Prove readiness.

**Warnings**

- Step 5 replaces the node's systemd unit and restarts the node. Step 6
  restarts it twice more. Expect a short loss of sync each time.
- ARM64 status: the node release used here ships an official arm64 build, but
  the ROKO team has not yet run its enrollment qualification fixture on arm64.
  amd64 is qualified. The steps are identical on both architectures. Please
  send back the evidence listed in [Report back](#report-back), because it
  helps qualify arm64.
- No inbound port, port-forward or public address is required. Do not open
  TCP/30333 or any RPC port for this procedure.
- Keep the wallet on a different machine. Never copy a seed phrase, keystore,
  wallet key or `/var/lib/roko` content to anyone, including support.

## System topology

| Item | Expected value |
|---|---|
| Hardware | NVIDIA Jetson (Orin family), `uname -m` = `aarch64` |
| OS | JetPack 6 (L4T R36, Ubuntu 22.04, glibc 2.35) or newer. JetPack 5 (glibc 2.31) cannot run the arm64 binary; see step 1 |
| Network | ROKO testnet `roko-testnet-v2`, runtime spec **286** |
| Node release | `nightly-f490bcd1-20261014`, source `f490bcd12df8af67e9bd009482fbc1954199d7f1`, version string `3.0.0-dev-f490bcd12df` |
| arm64 native bundle | `roko-node-testnet-linux-arm64.tar.gz`, SHA-256 `512d489e0c1382434614b404a3ba0e64bb3747351b5e857beab33989ba9a28d4` |
| arm64 `roko-node` binary | SHA-256 `272d20659a047a530280a4fa9018cf16f450ec3fffecb3b669af336856a74fc2` |
| Enrollment tools | 1.4.7 from `https://downloads.roko.network/validator-tools/1.4.7/` |
| Release signing key | fingerprint `62297562B1C7053088F405DB0117DAAA677A5BF2` |
| Paths used by the supported unit | binary `/usr/local/bin/roko-node`, chain spec `/etc/roko/roko-testnet-v2.json`, data `/var/lib/roko`, unit `/etc/systemd/system/roko-node.service`, RPC policy `/etc/roko/node-rpc.env` |
| Clock | Chrony installed and synchronized (or an active, licensed Timebeat) |

## Procedure

Run everything as a sudo-capable user on the Jetson unless a step says
"wallet machine". Work in one directory:

```bash
mkdir -p ~/roko-enroll && cd ~/roko-enroll
```

### 1. Preflight

```bash
uname -m
cat /etc/nv_tegra_release
ldd --version | head -1
chronyc tracking | grep -E 'Leap status|System time'
```

Expected:

```
aarch64
# R36 (release), ...                 <- JetPack 6
ldd (Ubuntu GLIBC 2.35-...) 2.35     <- 2.34 or newer required
Leap status     : Normal
System time     : 0.000xxxxx seconds ...   (well under 10 ms)
```

**Stop here if you see R35 or glibc older than 2.34 (JetPack 5).** The arm64
`roko-node` binary needs glibc 2.34. The enrollment tools also run that binary
directly to record its identity, so a Docker-only node can't enroll either.
Upgrade the Jetson to JetPack 6 first; Orin modules support it.

Find how the node runs today, and record it before changing anything:

```bash
systemctl list-units --type=service | grep -i roko
UNIT=roko-node.service          # change if the line above shows another name
systemctl cat "$UNIT" > ~/roko-enroll/unit-before.txt
grep -E -- '--base-path|--chain|--rpc-methods|EnvironmentFile|ExecStart' ~/roko-enroll/unit-before.txt
```

**Stop here and ask** if `--base-path` is not `/var/lib/roko` or `--chain` is
not `/etc/roko/roko-testnet-v2.json`. Step 3 renders the supported unit with
those paths. Pointing it at an empty data directory would trigger a full resync.

### 2. Pin the node binary to the network release

Check the running binary first:

```bash
/usr/local/bin/roko-node --version
sha256sum /usr/local/bin/roko-node
```

Expected: the version contains `3.0.0-dev-f490bcd12df` and the SHA-256 is
`272d20659a047a530280a4fa9018cf16f450ec3fffecb3b669af336856a74fc2`. If both
match, skip to step 3.

Otherwise, native path:

```bash
B=https://downloads.roko.network/releases/nightly-f490bcd1-20261014
curl --fail --location --remote-name "$B/roko-node-testnet-linux-arm64.tar.gz"
echo "512d489e0c1382434614b404a3ba0e64bb3747351b5e857beab33989ba9a28d4  roko-node-testnet-linux-arm64.tar.gz" | sha256sum --check --strict
mkdir node-arm64 && tar -xzf roko-node-testnet-linux-arm64.tar.gz -C node-arm64
echo "272d20659a047a530280a4fa9018cf16f450ec3fffecb3b669af336856a74fc2  node-arm64/roko-node" | sha256sum --check --strict
node-arm64/roko-node --version
```

Expected: `OK` twice, then a version containing `3.0.0-dev-f490bcd12df`.

```bash
sudo systemctl stop "$UNIT"
sudo install -m 0755 -o root -g root node-arm64/roko-node /usr/local/bin/roko-node
sudo systemctl start "$UNIT"
```

### 3. Install the signed enrollment tools 1.4.7

Verify the signed manifest before running anything:

```bash
T=https://downloads.roko.network/validator-tools/1.4.7
for f in install-roko-validator-enroll.sh SHA256SUMS SHA256SUMS.asc roko-release-signing-key.asc; do
  curl --fail --location --remote-name "$T/$f"
done
export ROKO_VERIFY_GNUPGHOME="$(mktemp -d)"
test "$(GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --with-colons --import-options show-only --import roko-release-signing-key.asc 2>/dev/null | awk -F: '$1=="fpr"{print toupper($10);exit}')" = 62297562B1C7053088F405DB0117DAAA677A5BF2 && echo key-ok
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --import roko-release-signing-key.asc
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" gpg --batch --verify SHA256SUMS.asc SHA256SUMS
awk '$2=="install-roko-validator-enroll.sh"{print}' SHA256SUMS | sha256sum --check --strict
sudo bash install-roko-validator-enroll.sh --release-base "$T"
roko-validator-enroll --version
```

Expected: `key-ok`, then `Good signature` from key `6229 7562 B1C7 0530 88F4
05DB 0117 DAAA 677A 5BF2`, then `install-roko-validator-enroll.sh: OK`, and
finally a version line ending in `1.4.7`.

### 4. Get the signed service installer and the authority peer list

The supported validator-candidate unit is rendered by the edge-tools installer
at the signed tag `v1.4.7`:

```bash
git clone --branch v1.4.7 --depth 1 https://github.com/Roko-Network/roko-edge-tools.git
GNUPGHOME="$ROKO_VERIFY_GNUPGHOME" git -C roko-edge-tools verify-tag v1.4.7
```

Expected: `Good signature` from the same fingerprint as in step 3.

Install the signed active-authority manifest. It lists the validators your node
reserves connections to:

```bash
NODE_ROLE=validator-candidate bash roko-edge-tools/installer/scripts/install-authority-peers.sh
python3 -c 'import json; v=json.load(open("/etc/roko/authority-peers.json")); print(len(v["authorities"]), "authorities; min mapped peers", v["minimumMappedPeers"])'
```

Expected: `Installed signed active-authority transport contract:
/etc/roko/authority-peers.json`, then two or more authorities.

### 5. Install the supported validator-candidate unit

The key-window helper in step 6 refuses any unit that hardcodes
`--rpc-methods Safe`. It needs all of the following:

- the policy file `/etc/roko/node-rpc.env`, owned by root, not group- or
  world-writable, containing exactly `ROKO_RPC_METHODS=Safe`;
- the unit lines `Environment=ROKO_RPC_METHODS=Safe` and
  `EnvironmentFile=-/etc/roko/node-rpc.env`;
- the literal `--rpc-methods ${ROKO_RPC_METHODS}` in `ExecStart`.

The 1.4.7 service installer renders all of these and creates the policy file
for you. Its validator-candidate unit also includes:

- the authority peers as reserved nodes;
- the `early-testnet` timing profile and the testnet timing thresholds;
- the corrected bootnode address without `/ws`;
- service hardening.

**5a. Preview the unit (no host change yet):**

```bash
ROKO_CHRONY_GID="$(sudo stat -c %g /run/chrony/chronyd.sock)" \
ROKO_AUTHORITY_ADDRESSES="$(python3 -c 'import json; [print(a) for x in json.load(open("/etc/roko/authority-peers.json"))["authorities"] for a in x["addresses"]]')" \
  bash roko-edge-tools/installer/scripts/install-roko-service.sh \
  --runtime native --node-name orin --clock-provider chrony \
  --validator-candidate --timing-profile early-testnet --render-unit > roko-node.service

grep -c -- '--reserved-nodes' roko-node.service
grep -E -- '--base-path|--chain' roko-node.service
grep -F -e 'Environment=ROKO_RPC_METHODS=Safe' -e 'EnvironmentFile=-/etc/roko/node-rpc.env' -e '--rpc-methods ${ROKO_RPC_METHODS}' roko-node.service
diff -u unit-before.txt roko-node.service | less
```

Replace `orin` with your node name if it's different. Expected output:

```
2            <- or more: one line per authority address
  --chain /etc/roko/roko-testnet-v2.json \
  --base-path /var/lib/roko \
Environment=ROKO_RPC_METHODS=Safe
EnvironmentFile=-/etc/roko/node-rpc.env
  --rpc-methods ${ROKO_RPC_METHODS}
```

**5b. Install.** This creates the `roko` service account if it's missing,
creates `/etc/roko/node-rpc.env` in Safe state, then writes and enables the
unit without starting it. Your current node keeps running until 5c.

```bash
sudo bash roko-edge-tools/installer/scripts/install-roko-service.sh \
  --runtime native --node-name orin --clock-provider chrony \
  --validator-candidate --timing-profile early-testnet
systemctl cat roko-node.service | grep -F -- '--rpc-methods ${ROKO_RPC_METHODS}'
sudo cat /etc/roko/node-rpc.env
```

Expected: the installer ends with `Installed /etc/systemd/system/roko-node.service`
and `RPC key-management policy: /etc/roko/node-rpc.env (Safe)`. The last two
commands print the `--rpc-methods ${ROKO_RPC_METHODS}` line and
`ROKO_RPC_METHODS=Safe`.

**5c. Switch over:**

1. Stop the old service. If the old unit had another name, also disable it so
   two nodes never share the data directory:

   ```bash
   sudo systemctl stop "$UNIT"
   [ "$UNIT" != roko-node.service ] && sudo systemctl disable "$UNIT"
   ```

2. Find out who owns the data directory:

   ```bash
   sudo stat -c '%U' /var/lib/roko/chains
   ```

3. If step 2 printed anything other than `roko`, the old unit ran as another
   user. Hand the data to the service account:

   ```bash
   sudo chown -R roko:roko /var/lib/roko
   ```

4. Start the new unit:

   ```bash
   sudo systemctl restart roko-node.service
   UNIT=roko-node.service
   systemctl is-active "$UNIT"
   ```

Expected: `active`. Wait until the node is back at the chain tip
(`journalctl -u roko-node -f` shows `Imported #...` at the current height), then
confirm the RPC lockdown:

```bash
roko-validator-enroll --rpc http://127.0.0.1:9944 --check-rpc-policy; echo "exit=$?"
```

Expected: `safe-restored`, `exit=0`.

### 6. Generate session keys in the guarded window

First confirm that nothing exposes local RPC: no reverse proxy, SSH tunnel, VPN
port-forward, Docker publish or relay pointing at port 9944. Then:

```bash
sudo roko-session-key-window \
  --service roko-node.service \
  --confirm-isolated-window --confirm-no-forwarding -- \
  --binary /usr/local/bin/roko-node \
  --output roko-validator-enrollment.json
```

The helper does the whole job:

1. Backs up the policy file.
2. Switches the policy to Unsafe and restarts the node.
3. Generates the keys and writes the package.
4. Restores Safe and restarts again.

Don't run `roko-validator-enroll` separately first. If keys already exist from
an earlier attempt, add `--reuse-session-keys 0x<PUBLIC_KEYS>` before `--` and
use a new output name.

Leave out `--public-address`. The tool falls back to the node's listen
addresses, and no inbound reachability is checked or required. If you choose to
publish an address anyway, the valid forms are `/dns4/<host>/tcp/30333/p2p/<PEER_ID>`
and `/ip4/<a.b.c.d>/tcp/30333/p2p/<PEER_ID>`.

Expected: the helper finishes and `roko-validator-enrollment.json` exists. Then:

```bash
roko-validator-enroll --rpc http://127.0.0.1:9944 --check-rpc-policy; echo "exit=$?"
```

Expected: `safe-restored`, `exit=0`. Note the public session-key tuple
(`0x...`) from the JSON; you need it in step 8.

### 7. Wallet machine: sign the four transactions

1. Copy `roko-validator-enrollment.json` (public, short-lived) to the wallet
   machine.
2. Open <https://agora.roko.network/participate/staking> and import the
   package.
3. Connect the staking (stash) account, then review and sign each transaction
   in order:
   1. `pwRoko.lock`
   2. `staking.bond`
   3. `session.setKeys`
   4. `staking.validate`
4. Wait until all four are finalized.

A finalized `staking.validate` means candidate intent only. Election and
authoring come later.

### 8. Prove readiness on the Jetson

```bash
roko-validator-enroll --rpc http://127.0.0.1:9944 \
  --check-account 0xYOUR_STASH_ACCOUNT \
  --expected-session-keys 0xPUBLIC_ENCODED_KEYS; echo "exit=$?"
roko-validator-enroll --rpc http://127.0.0.1:9944 \
  --save-readiness ./roko-validator-readiness.json
```

Expected: `exit=0` means local key custody plus finalized bond, intent and
matching next-session keys. `exit=2` is a normal "not ready yet": read the JSON
fields, wait or fix the missing step, and rerun. Import
`roko-validator-readiness.json` in Agora's **Import validator readiness**
panel.

## Verification

After election, which can take one or more sessions, check all of these:

- `systemctl is-active roko-node` prints `active`.
- `roko-validator-enroll --check-rpc-policy` exits `0` with `safe-restored`.
- Agora shows the account move from candidate or waiting to active, then shows
  finalized authored blocks.
- `roko-validator-watch` (post-activation monitor) reports active-session
  authorship.

## Troubleshooting

- **`GLIBC_2.34 not found`**: JetPack 5. Upgrade to JetPack 6; see step 1.
- **Key window: `service lacks the default Safe policy`,
  `does not consume the selected policy file` or `does not bind rpc-methods`**:
  the unit is not the supported contract. Redo step 5. Don't hand-edit around it.
- **Key window: `service contains a public RPC exposure flag`**: remove
  `--rpc-external`, `--unsafe-rpc-external` or any `--rpc-listen-address`
  0.0.0.0 setting. RPC must stay loopback-only.
- **`--check-rpc-policy` exits 2**: key-management RPC is still reachable. Stop
  and restore `/etc/roko/node-rpc.env` to exactly `ROKO_RPC_METHODS=Safe`,
  then restart.
- **`Validator-candidate service requires at least two published authority
  addresses`** or a manifest error: rerun step 4. The manifest is short-lived;
  refresh it, don't edit it.
- **Readiness shows few authority peers or timing quality 0**: the Jetson needs
  stable outbound connections to at least two active authorities, because
  timing probes are point-to-point. WiFi jitter is the usual cause. Use a
  wired link if you can. Opening inbound ports does not help.
- **`/etc/roko/node-rpc.env must be restored to exact Safe state`** (or must
  be owned by root, or not group- or world-writable) in step 5b: an earlier
  policy file exists. Stop and report it; don't delete or edit it to get past
  the check.
- **Node won't start after step 5**: run `journalctl -u roko-node -n 100`.
  `Permission denied` under `/var/lib/roko` means 5c step 3 was skipped. To roll
  back, `sudo systemctl disable --now roko-node`, then re-enable and start your
  old unit. Its original text is saved in `~/roko-enroll/unit-before.txt`.

## House rules for agents

- DO run the steps in order and compare every output with its "Expected" block
  before continuing.
- DO stop and report on any checksum, signature or `--check-rpc-policy`
  failure.
- DON'T build `roko-node` from source, download from mirrors, or substitute a
  binary whose SHA-256 differs from the table.
- DON'T open ports, add port-forwards, or expose RPC beyond 127.0.0.1.
- DON'T create `/etc/roko/node-rpc.env` by hand to satisfy the key window, and
  don't hand-edit the enrollment or readiness JSON.
- DON'T move wallet keys or seed phrases onto the Jetson.

## What NOT to fix

- **Absent `--public-address`**: intentional. Outbound-only validators are
  supported.
- **Node on testnet runtime 286**: correct. Tools 1.4.7 accept exactly runtime
  spec 286; don't upgrade to unreleased builds. Tooling 1.4.8 for runtime 290
  is unpublished; this runbook will be revised when runtime 290 is delivered.
- **Enrollment JSON expires**: by design. Generate a fresh package with
  `--reuse-session-keys` rather than rotating keys.

## Report back

Please send these value-free facts back. They contain no secrets and help
qualify arm64:

```bash
{
  uname -m; cat /etc/nv_tegra_release; ldd --version | head -1
  /usr/local/bin/roko-node --version 2>/dev/null; sha256sum /usr/local/bin/roko-node 2>/dev/null
  roko-validator-enroll --version
  roko-validator-enroll --rpc http://127.0.0.1:9944 --check-rpc-policy; echo "check-rpc-policy exit=$?"
} > roko-arm64-report.txt 2>&1
```

Send `roko-arm64-report.txt` along with the exit codes from steps 6 and 8, plus
`roko-validator-readiness.json`, which is designed to be shared. Don't send the
keystore, wallet files or `/var/lib/roko`.

## Audit trail

| Field | Value |
|---|---|
| Prepared | 2026-10-15; revised 2026-10-16 for tools 1.4.7 |
| Applies to | Jetson arm64 hosts joining `roko-testnet-v2`, runtime spec 286 |
| Node release | `nightly-f490bcd1-20261014` |
| Tools release | `roko-edge-tools` v1.4.7 (signed tag; amd64 enrollment-qualified, arm64 pending) |
| Last verified | 2026-10-16, 1.4.7 artifacts checked against the published release |
