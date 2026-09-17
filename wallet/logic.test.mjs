import test from 'node:test';
import assert from 'node:assert/strict';
import { requireLoopback, nextStep, finalized } from './logic.mjs';

test('only literal loopback websocket connections are allowed', () => {
  requireLoopback('ws://127.0.0.1:9944');
  requireLoopback('ws://[::1]:9944');
  for (const value of ['ws://rpc.roko.network', 'ws://127.0.0.1.evil.com', 'ws://user@127.0.0.1', 'https://127.0.0.1', 'ws://127.0.0.1/?secret=x']) assert.throws(() => requireLoopback(value));
});
test('partial completion resumes each step and never rotates keys', () => {
  const state = { pw: 0n, bonded: false, active: 0n, keys: null, intent: false };
  assert.deepEqual(nextStep(state, 50n, '0xab'), ['lock', 50n]);
  state.pw = 50n;
  assert.deepEqual(nextStep(state, 50n, '0xab'), ['bond', 50n]);
  state.bonded = true; state.active = 50n;
  assert.deepEqual(nextStep(state, 50n, '0xab'), ['setKeys', '0xab']);
  state.keys = '0xab';
  assert.deepEqual(nextStep(state, 50n, '0xab'), ['validate']);
  state.intent = true;
  assert.equal(nextStep(state, 50n, '0xab'), null);
  assert.throws(() => nextStep(state, 50n, '0xcd'), /cannot rotate/);
  assert.throws(() => nextStep(state, 51n, '0xab'), /below requested/);
});
test('finalization handles callbacks before subscription resolves', async () => {
  let unsubscribed = false;
  const receipts = [];
  const tx = { hash: { toHex: () => '0xtx' }, signAndSend: async (_s, _o, callback) => {
    callback({ status: { isFinalized: true, asFinalized: { toHex: () => '0xblock' } }, events: [] });
    return () => { unsubscribed = true; };
  } };
  assert.deepEqual(await finalized(tx, {}, 180000, receipt => receipts.push(receipt)), { transactionHash: '0xtx', finalizedHash: '0xblock' });
  await Promise.resolve();
  assert.equal(unsubscribed, true);
  assert.deepEqual(receipts, [{ transactionHash: '0xtx', status: 'submitted; awaiting finalization' }]);
});
test('dispatch errors and timeouts never report success', async () => {
  const failed = { hash: { toHex: () => '0xtx' }, signAndSend: async (_s, _o, cb) => { cb({ status: { isFinalized: true, asFinalized: { toHex: () => '0xblock' } }, dispatchError: {}, events: [] }); return () => {}; } };
  await assert.rejects(finalized(failed, {}), /dispatch failure/);
  let stopped = false;
  await assert.rejects(finalized({ signAndSend: async () => () => { stopped = true; } }, {}, 5), /outcome unknown/);
  assert.equal(stopped, true);
});
