export const GENESIS = '0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb';
export function requireLoopback(value) {
  const url = new URL(value);
  if (url.protocol !== 'ws:' || !['127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Use a loopback ws://127.0.0.1:9944 RPC URL');
  }
}
export function nextStep(state, stake, keys) {
  if (state.keys && state.keys.toLowerCase() !== keys.toLowerCase()) throw new Error('Existing session keys differ; this tool cannot rotate keys');
  if (state.bonded && state.active < stake) throw new Error('Existing bond is below requested stake; review staking ledger before continuing');
  if (!state.bonded) {
    if (state.pw < stake) return ['lock', stake - state.pw];
    return ['bond', stake];
  }
  if (!state.keys) return ['setKeys', keys];
  if (!state.intent) return ['validate'];
  return null;
}
export async function finalized(tx, signer, timeoutMs = 180000, onSubmitted = () => {}) {
  return new Promise((resolve, reject) => {
    let unsubscribe, done = false, reported = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      unsubscribe?.();
      error ? reject(error) : resolve(value);
    };
    const timer = setTimeout(() => finish(new Error('Finalization timed out; transaction outcome unknown. Check finalized state and pending nonce before retrying.')), timeoutMs);
    tx.signAndSend(signer, { nonce: -1 }, result => {
      if (!reported) {
        reported = true;
        onSubmitted({ transactionHash: tx.hash.toHex(), status: 'submitted; awaiting finalization' });
      }
      if (result.status.isInvalid || result.status.isDropped || result.status.isUsurped) return finish(new Error('Transaction rejected or replaced; inspect account activity before retrying'));
      if (!result.status.isFinalized) return;
      if (result.dispatchError || result.events.some(({ event }) => event.section === 'system' && event.method === 'ExtrinsicFailed')) return finish(new Error(`Transaction ${tx.hash.toHex()} finalized in ${result.status.asFinalized.toHex()} with a dispatch failure; inspect the explorer before retrying`));
      finish(null, { transactionHash: tx.hash.toHex(), finalizedHash: result.status.asFinalized.toHex() });
    }).then(unsub => { unsubscribe = unsub; if (done) unsub(); }, () => finish(new Error('Submission failed; inspect account activity before retrying')));
  });
}
