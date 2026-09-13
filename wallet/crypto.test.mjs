import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, statSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Keyring } from '@polkadot/api';
import { cryptoWaitReady, secp256k1Compress } from '@polkadot/util-crypto';

test('exact raw ECDSA seed creates a private encrypted wallet and cannot overwrite it', async () => {
  await cryptoWaitReady();
  // Public deterministic fixture; never use this account on a real network.
  const seed = '0x' + '01'.repeat(32);
  const password = 'test-only-password';
  const pair = new Keyring({ type: 'ethereum' }).addFromUri(seed);
  const nodePublicKey = '0x' + Buffer.from(secp256k1Compress(pair.publicKey)).toString('hex');
  const dir = mkdtempSync(join(tmpdir(), 'roko-wallet-test-'));
  try {
    const wallet = join(dir, 'encrypted.json');
    const input = JSON.stringify({ command: 'create', seed, password, nodePublicKey, wallet });
    const created = spawnSync(process.execPath, ['cli.mjs'], { input, encoding: 'utf8' });
    assert.equal(created.status, 0, created.stderr);
    assert.equal(JSON.parse(created.stdout).account, pair.address);
    assert.equal(statSync(wallet).mode & 0o777, 0o600);
    const json = JSON.parse(readFileSync(wallet));
    assert.equal(JSON.stringify(json).includes(seed.slice(2)), false);
    const restored = new Keyring({ type: 'ethereum' }).addFromJson(json);
    assert.throws(() => restored.decodePkcs8('wrong-password'));
    restored.decodePkcs8(password);
    assert.equal(restored.address, pair.address);
    const signature = restored.sign(new Uint8Array(32));
    assert.ok(pair.verify(new Uint8Array(32), signature, pair.publicKey));
    const duplicate = spawnSync(process.execPath, ['cli.mjs'], { input, encoding: 'utf8' });
    assert.notEqual(duplicate.status, 0);
    for (const output of [created.stdout, created.stderr, duplicate.stdout, duplicate.stderr]) {
      assert.equal(output.includes(seed), false);
      assert.equal(output.includes(password), false);
    }
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
