// Opt-in, read-only live metadata/encoding check. Never signs or submits.
import assert from 'node:assert/strict';
import { ApiPromise, HttpProvider } from '@polkadot/api';
import { GENESIS } from './logic.mjs';
const deadline = setTimeout(() => process.exit(1), 45000);
const api = await ApiPromise.create({ provider: new HttpProvider('https://rpc.roko.network'), noInitWarn: true });
try {
  assert.equal(api.genesisHash.toHex(), GENESIS);
  const calls = [api.tx.pwRoko.lock(50000000000000000000n), api.tx.staking.bond(50000000000000000000n, 'Staked'), api.tx.session.setKeys('0x' + '11'.repeat(226), '0x'), api.tx.staking.validate({ commission: 0, blocked: false })];
  for (const tx of calls) assert.equal(api.createType('Call', tx.method.toHex()).toHex(), tx.method.toHex());
  const head = await api.rpc.chain.getFinalizedHead();
  const at = await api.at(head);
  const account = '0x' + '00'.repeat(20);
  const [balance, pw, bonded, keys, intent, minimum] = await Promise.all([at.query.system.account(account), at.query.pwRoko.balances(account), at.query.staking.bonded(account), at.query.session.nextKeys(account), api.rpc.state.getStorage(at.query.staking.validators.key(account), head), at.query.staking.minValidatorBond()]);
  assert.equal(typeof balance.data.free.toBigInt(), 'bigint');
  assert.equal(typeof pw.toBigInt(), 'bigint');
  for (const value of [bonded, keys, intent]) assert.equal(typeof value.isSome, 'boolean');
  console.log(JSON.stringify({ genesis: GENESIS, specVersion: api.runtimeVersion.specVersion.toString(), transactionVersion: api.runtimeVersion.transactionVersion.toString(), minimumValidatorBond: minimum.toString(), encodedCalls: calls.map(tx => tx.method.section + '.' + tx.method.method), finalizedHash: head.toHex(), submitted: false }));
} finally { clearTimeout(deadline); await api.disconnect(); }
