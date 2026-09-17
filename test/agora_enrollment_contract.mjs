#!/usr/bin/env node
// Run the actual, separately pinned Agora validator against a live CLI package.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const [modulePath, expectedSha] = process.argv.slice(2);
const source = readFileSync(modulePath);
assert.match(expectedSha, /^[0-9a-f]{64}$/);
assert.equal(createHash('sha256').update(source).digest('hex'), expectedSha);
// This validator is standalone. Import exactly the bytes whose digest was checked.
const {validateValidatorEnrollment} = await import(`data:text/javascript;base64,${source.toString('base64')}`);
const {package: enrollment, expected} = JSON.parse(readFileSync(0, 'utf8'));
await validateValidatorEnrollment(enrollment, {expected});
const rejected = {};
const cases = [
  ['wrongGenesis', enrollment, {expected: {...expected, genesisHash: `0x${'00'.repeat(32)}`}}, 'network.genesisHash'],
  ['wrongRuntime', enrollment, {expected: {...expected, specVersion: expected.specVersion + 1}}, 'network.specVersion'],
  ['wrongMetadata', enrollment, {expected: {...expected, metadataHash: `0x${'00'.repeat(32)}`}}, 'network.metadataHash'],
  ['expired', enrollment, {now: Date.parse(enrollment.expiresAt) + 1}, 'time.expired'],
  ['tampered', {...enrollment, enrollmentId: `0x${'00'.repeat(32)}`}, {expected}, 'integrity.mismatch'],
  ['replayed', enrollment, {expected, usedDigests: [enrollment.integrity.digest]}, 'integrity.replay'],
];
for (const [name, value, options, code] of cases) {
  await assert.rejects(() => validateValidatorEnrollment(value, options), error => error.code === code);
  rejected[name] = code;
}
console.log(JSON.stringify({
  scope: 'actual Agora validator module in Node; no browser or wallet signing',
  moduleSha256: expectedSha, accepted: true,
  packageDigest: enrollment.integrity.digest, expected, rejected,
}));
