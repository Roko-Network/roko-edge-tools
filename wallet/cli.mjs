import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { ApiPromise, WsProvider, Keyring } from '@polkadot/api';
import { cryptoWaitReady, secp256k1Compress } from '@polkadot/util-crypto';
import { GENESIS, requireLoopback, nextStep, finalized } from './logic.mjs';

async function main() {
  const args = JSON.parse(fs.readFileSync(0, 'utf8'));
  await cryptoWaitReady();
  const keyring = new Keyring({ type: 'ethereum' });
  if (args.command === 'create') {
    if (!/^0x[0-9a-fA-F]{64}$/.test(args.seed)) throw new Error('Invalid node secret seed');
    const pair = keyring.addFromUri(args.seed);
    const compressed = `0x${Buffer.from(secp256k1Compress(pair.publicKey)).toString('hex')}`;
    if (compressed.toLowerCase() !== args.nodePublicKey.toLowerCase()) throw new Error('Node public key does not match wallet');
    fs.writeFileSync(args.wallet, JSON.stringify(pair.toJson(args.password), null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(JSON.stringify({ account: pair.address, wallet: args.wallet, encrypted: true }));
    pair.lock();
    return;
  }
  requireLoopback(args.rpc);
  if (!/^0x[0-9a-fA-F]{40}$/.test(args.account)) throw new Error('Expected AccountId20 address');
  if (!/^[1-9][0-9]*$/.test(args.stake_planck)) throw new Error('Stake must be a positive integer in planck');
  const stake = BigInt(args.stake_planck);
  const pkg = args.package;
  if (pkg.network.genesisHash !== GENESIS) throw new Error('Enrollment package is not for the supported testnet');
  let signer;
  if (args.command === 'enroll') {
    if (!args.execute) throw new Error('Execution was not confirmed');
    const stat = fs.lstatSync(args.wallet);
    if (!stat.isFile() || (stat.mode & 0o077)) throw new Error('Wallet must be a regular private file (chmod 600)');
    try {
      signer = keyring.addFromJson(JSON.parse(fs.readFileSync(args.wallet, 'utf8')));
      signer.decodePkcs8(args.password);
    } catch { throw new Error('Cannot unlock encrypted wallet'); }
    if (signer.address.toLowerCase() !== args.account.toLowerCase()) throw new Error('Wallet address differs from --account');
  }
  const provider = new WsProvider(args.rpc, false, {}, 15000);
  const deadline = setTimeout(() => { console.error('RPC operation timed out; inspect finalized state before retrying'); process.exit(1); }, 900000);
  let api;
  try {
    await provider.connect();
    api = await ApiPromise.create({ provider, noInitWarn: true });
    // Require current finality progress before preparing any enrollment call.
    const initialHead = (await api.rpc.chain.getFinalizedHead()).toHex();
    let advancing = false;
    for (let attempt = 0; attempt < 15; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      if ((await api.rpc.chain.getFinalizedHead()).toHex() !== initialHead) { advancing = true; break; }
    }
    if (!advancing) throw new Error('Finality did not advance within 30 seconds; resolve node health before enrollment');
    for (let iteration = 0; iteration < 5; iteration++) {
      if (Date.now() >= Date.parse(pkg.expiresAt)) throw new Error('Enrollment package expired; generate a fresh package using the same session keys');
      const [genesis, runtime, metadata, peer, health] = await Promise.all([
        api.rpc.chain.getBlockHash(0), api.rpc.state.getRuntimeVersion(), api.rpc.state.getMetadata(), api.rpc.system.localPeerId(), api.rpc.system.health(),
      ]);
      const hash = '0x' + createHash('sha256').update(Buffer.from(metadata.toHex().slice(2), 'hex')).digest('hex');
      if (genesis.toHex() !== GENESIS || runtime.specVersion.toNumber() !== pkg.network.specVersion || runtime.transactionVersion.toNumber() !== pkg.network.transactionVersion || hash !== pkg.network.metadataHash) throw new Error('Live chain/runtime differs from enrollment package; regenerate it');
      if (peer.toString() !== pkg.node.peerId || health.isSyncing.isTrue || health.peers.toNumber() < 1) throw new Error('Wrong node, syncing, or no peers');
      const head = await api.rpc.chain.getFinalizedHead();
      const at = await api.at(head);
      const [account, pw, bonded, keys, intentRaw, min, pending] = await Promise.all([
        at.query.system.account(args.account), at.query.pwRoko.balances(args.account), at.query.staking.bonded(args.account), at.query.session.nextKeys(args.account), api.rpc.state.getStorage(at.query.staking.validators.key(args.account), head), at.query.staking.minValidatorBond(), api.rpc.system.accountNextIndex(args.account),
      ]);
      if (pending.toString() !== account.nonce.toString()) throw new Error('Account has unfinalized transactions; wait before retrying');
      if (stake < min.toBigInt()) throw new Error('Requested stake is below live minimum validator bond');
      if (bonded.isSome && bonded.unwrap().toString().toLowerCase() !== args.account.toLowerCase()) throw new Error('Existing staking controller differs; this tool supports self-controlled staking accounts');
      const ledger = bonded.isSome ? await at.query.staking.ledger(bonded.unwrap()) : null;
      if (bonded.isSome && ledger.isNone) throw new Error('Bonded account has no staking ledger');
      const state = { pw: pw.toBigInt(), bonded: bonded.isSome, active: ledger?.isSome ? ledger.unwrap().active.toBigInt() : 0n, keys: keys.isSome ? keys.unwrap().toHex() : null, intent: intentRaw.isSome };
      const step = nextStep(state, stake, pkg.session.encodedKeys);
      if (!step) { console.log(JSON.stringify({ account: args.account, status: 'candidate registration finalized', finalizedHash: head.toHex(), note: 'Election, validator mode, and block authorship still require verification.' })); return; }
      const calls = { lock: () => api.tx.pwRoko.lock(step[1]), bond: () => api.tx.staking.bond(step[1], 'Staked'), setKeys: () => api.tx.session.setKeys(step[1], '0x'), validate: () => api.tx.staking.validate({ commission: 0, blocked: false }) };
      const tx = calls[step[0]]();
      const fee = (await tx.paymentInfo(args.account)).partialFee.toBigInt();
      const reserve = api.consts.balances.existentialDeposit.toBigInt() + fee * 2n;
      const frozen = account.data.frozen?.toBigInt() ?? 0n;
      const required = reserve + (step[0] === 'lock' ? step[1] : 0n);
      console.log(JSON.stringify({ account: args.account, nextCall: step[0], callData: tx.method.toHex(), estimatedFeePlanck: fee.toString(), nativeRequiredPlanck: required.toString(), nativeFreePlanck: account.data.free.toString(), remainingSequence: ['lock if needed', 'bond if needed', 'setKeys if needed', 'validate if needed'] }));
      if (account.data.free.toBigInt() - frozen < required) throw new Error('Insufficient spendable native ROKO for this step and fee reserve; fund the displayed account');
      if (args.command === 'plan') return;
      console.log(JSON.stringify({ call: step[0], ...await finalized(tx, signer) }));
    }
    throw new Error('State did not converge after four enrollment calls; review receipts');
  } finally { clearTimeout(deadline); signer?.lock(); if (api) await api.disconnect(); else await provider.disconnect(); }
}
main().catch(error => { console.error(`roko-validator-wallet: ${error.message}`); process.exitCode = 1; });
