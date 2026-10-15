const SCHEMA = "roko.validator-enrollment.v1";
const HASH = /^0x[0-9a-f]{64}$/i;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const DECIMAL = /^(?:0|[1-9][0-9]*)$/;
const HEX_BYTES = /^0x(?:[0-9a-f]{2}){32,1024}$/i;
const KEY_TYPES = Object.freeze(["grandpa", "babe", "imOnline", "authorityDiscovery", "mixnet", "beefy", "temporal"]);
const MAX_PACKAGE_AGE_MS = 24 * 60 * 60 * 1000;
const CLOCK_SKEW_MS = 5 * 60 * 1000;

export const VALIDATOR_ENROLLMENT_SCHEMA = SCHEMA;
export const VALIDATOR_SESSION_KEY_TYPES = KEY_TYPES;
export const VALIDATOR_PERMISSIONLESS_CALLS = Object.freeze([
  "pwRoko.lock",
  "staking.bond",
  "session.setKeys",
  "staking.validate",
  "staking.chill",
  "staking.unbond",
  "staking.withdrawUnbonded",
]);
export const VALIDATOR_PROHIBITED_CALLS = Object.freeze([
  "sudo.sudo",
  "staking.setInvulnerables",
  "staking.setValidatorCount",
  "staking.forceNewEra",
  "staking.forceNoEras",
]);

const PROHIBITED_KEYS = /(?:secret|private|seed|mnemonic|phrase|suri|keystore|vault|openbao|token|password|cookie|approle|nodekey)/i;

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function object(value, path) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("shape.object", `${path} must be an object.`);
  return value;
}

function exact(value, keys, path) {
  const record = object(value, path);
  const expected = new Set(keys);
  for (const key of Object.keys(record)) if (!expected.has(key)) fail("shape.unknown", `${path} contains unsupported field "${key}".`);
  for (const key of keys) if (!Object.hasOwn(record, key)) fail("shape.missing", `${path} is missing "${key}".`);
  return record;
}

function string(value, pattern, path, maximum = 512) {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum || (pattern && !pattern.test(value))) {
    fail("shape.string", `${path} has an invalid value.`);
  }
  return value;
}

function integer(value, minimum, path) {
  if (!Number.isSafeInteger(value) || value < minimum) fail("shape.integer", `${path} must be an integer greater than or equal to ${minimum}.`);
  return value;
}

function boolean(value, expected, path) {
  if (value !== expected) fail("readiness.failed", `${path} must be ${expected}.`);
}

function scan(value, path = "$") {
  if (Array.isArray(value)) return value.forEach((entry, index) => scan(entry, `${path}[${index}]`));
  if (!value || typeof value !== "object") return;
  for (const [key, entry] of Object.entries(value)) {
    if (PROHIBITED_KEYS.test(key) && !["hasSessionKeys"].includes(key)) fail("security.prohibited-field", `${path} contains prohibited field "${key}".`);
    scan(entry, `${path}.${key}`);
  }
}

export function canonicalizeEnrollmentValue(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("canonical.number", "Enrollment numbers must be safe integers.");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalizeEnrollmentValue);
  const record = object(value, "$");
  return Object.fromEntries(Object.keys(record).sort().map((key) => [key, canonicalizeEnrollmentValue(record[key])]));
}

export function canonicalEnrollmentJson(value) {
  return JSON.stringify(canonicalizeEnrollmentValue(value));
}

export function enrollmentPayload(value) {
  const record = object(value, "$");
  const { integrity: _integrity, ...payload } = record;
  return payload;
}

export async function sha256Hex(value) {
  return sha256HexBytes(new TextEncoder().encode(value));
}

export async function sha256HexBytes(bytes) {
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", bytes));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function digestEnrollmentPackage(value) {
  return `sha256:${await sha256Hex(canonicalEnrollmentJson(enrollmentPayload(value)))}`;
}

function validateTimestamp(generatedAt, expiresAt, now) {
  const generated = Date.parse(generatedAt);
  const expires = Date.parse(expiresAt);
  if (!Number.isFinite(generated) || !Number.isFinite(expires)) fail("time.invalid", "Enrollment timestamps must be valid ISO-8601 values.");
  if (expires <= generated || expires - generated > MAX_PACKAGE_AGE_MS) fail("time.window", "Enrollment expiry must be after generation and no more than 24 hours later.");
  if (generated > now + CLOCK_SKEW_MS) fail("time.future", "Enrollment package was generated too far in the future.");
  if (expires <= now) fail("time.expired", "Enrollment package has expired. Generate fresh node session material.");
}

function validateExpected(network, expected = {}) {
  const comparisons = [
    ["chainName", expected.chainName],
    ["genesisHash", expected.genesisHash],
    ["specName", expected.specName],
    ["specVersion", expected.specVersion],
    ["transactionVersion", expected.transactionVersion],
    ["metadataHash", expected.metadataHash],
  ];
  for (const [field, wanted] of comparisons) {
    if (wanted === undefined || wanted === null) continue;
    const observed = network[field];
    const matches = typeof observed === "string" ? observed.toLowerCase() === String(wanted).toLowerCase() : observed === wanted;
    if (!matches) fail(`network.${field}`, `Enrollment ${field} does not match the connected ROKO network.`);
  }
}

export async function validateValidatorEnrollment(value, options = {}) {
  scan(value);
  const enrollment = exact(value, ["schema", "enrollmentId", "generatedAt", "expiresAt", "network", "node", "session", "integrity"], "$");
  if (enrollment.schema !== SCHEMA) fail("schema.unsupported", `Unsupported validator enrollment schema "${enrollment.schema}".`);
  string(enrollment.enrollmentId, HASH, "$.enrollmentId");
  string(enrollment.generatedAt, null, "$.generatedAt");
  string(enrollment.expiresAt, null, "$.expiresAt");
  validateTimestamp(enrollment.generatedAt, enrollment.expiresAt, options.now ?? Date.now());

  const network = exact(enrollment.network, ["chainName", "genesisHash", "specName", "specVersion", "transactionVersion", "metadataHash"], "$.network");
  string(network.chainName, null, "$.network.chainName", 128);
  string(network.genesisHash, HASH, "$.network.genesisHash");
  string(network.specName, null, "$.network.specName", 128);
  integer(network.specVersion, 1, "$.network.specVersion");
  integer(network.transactionVersion, 1, "$.network.transactionVersion");
  string(network.metadataHash, HASH, "$.network.metadataHash");
  validateExpected(network, options.expected);

  const node = exact(enrollment.node, ["peerId", "publicAddresses", "binaryVersion", "binarySha256", "role", "rpcExposure", "health"], "$.node");
  string(node.peerId, /^.{10,128}$/, "$.node.peerId", 128);
  if (!Array.isArray(node.publicAddresses) || node.publicAddresses.length > 32 || new Set(node.publicAddresses).size !== node.publicAddresses.length) fail("shape.addresses", "$.node.publicAddresses must be a unique array of at most 32 values.");
  node.publicAddresses.forEach((address, index) => string(address, /^\/.+/, `$.node.publicAddresses[${index}]`));
  string(node.binaryVersion, null, "$.node.binaryVersion", 256);
  string(node.binarySha256, HASH, "$.node.binarySha256");
  if (node.role !== "non-authoring") fail("node.role", "Enrollment must be generated while the node is non-authoring.");
  if (node.rpcExposure !== "loopback-only") fail("node.rpc", "Author RPC must be loopback-only.");
  const health = exact(node.health, ["isSyncing", "peers", "bestHeight", "finalizedHeight", "finalityAdvancing", "clockSynchronized", "p2pReachable"], "$.node.health");
  boolean(health.isSyncing, false, "$.node.health.isSyncing");
  integer(health.peers, 1, "$.node.health.peers");
  string(health.bestHeight, DECIMAL, "$.node.health.bestHeight");
  string(health.finalizedHeight, DECIMAL, "$.node.health.finalizedHeight");
  if (BigInt(health.finalizedHeight) > BigInt(health.bestHeight)) fail("readiness.height", "Finalized height cannot exceed best height.");
  boolean(health.finalityAdvancing, true, "$.node.health.finalityAdvancing");
  boolean(health.clockSynchronized, true, "$.node.health.clockSynchronized");
  boolean(health.p2pReachable, true, "$.node.health.p2pReachable");

  const session = exact(enrollment.session, ["encodedKeys", "keyTypes", "proofMode", "proof", "hasSessionKeys"], "$.session");
  string(session.encodedKeys, HEX_BYTES, "$.session.encodedKeys", 2050);
  if (!Array.isArray(session.keyTypes) || session.keyTypes.length !== KEY_TYPES.length || session.keyTypes.some((entry, index) => entry !== KEY_TYPES[index])) fail("session.key-types", "Session key types do not match the ROKO runtime tuple.");
  if (session.proofMode !== "legacy-empty" || session.proof !== "0x") fail("session.proof", "This ROKO runtime requires the explicit legacy-empty proof mode.");
  boolean(session.hasSessionKeys, true, "$.session.hasSessionKeys");

  const integrity = exact(enrollment.integrity, ["algorithm", "digest"], "$.integrity");
  if (integrity.algorithm !== "sha256") fail("integrity.algorithm", "Only SHA-256 enrollment integrity is supported.");
  string(integrity.digest, DIGEST, "$.integrity.digest");
  const calculated = await digestEnrollmentPackage(enrollment);
  if (calculated !== integrity.digest) fail("integrity.mismatch", "Enrollment package digest does not match its canonical public payload.");
  const used = new Set([...(options.usedDigests ?? [])].map((entry) => String(entry).toLowerCase()));
  if (used.has(integrity.digest.toLowerCase())) fail("integrity.replay", "This enrollment package was already used. Generate a fresh package.");

  return canonicalizeEnrollmentValue(enrollment);
}

export async function createValidatorEnrollment(payload, options = {}) {
  const packageWithoutIntegrity = { ...payload };
  const enrollment = {
    ...packageWithoutIntegrity,
    integrity: { algorithm: "sha256", digest: await digestEnrollmentPackage(packageWithoutIntegrity) },
  };
  return validateValidatorEnrollment(enrollment, options);
}

export function classifyValidatorLifecycle(facts) {
  if (facts.withdrawn && !facts.bonded && !facts.validatorIntent) return "exited";
  if (facts.withdrawable) return "withdrawable";
  if (facts.unbonding) return "unbonding";
  if (facts.chilled && facts.bonded) return "chilled";
  if (facts.active && facts.authoredFinalizedBlock && facts.finalityObserved) return "operational";
  if (facts.active) return "active";
  if (facts.elected) return "elected";
  if (facts.queued) return "queued";
  if (facts.validatorIntent && facts.sessionKeysSet) return "waiting";
  if (facts.validatorIntent) return "candidate";
  if (facts.bonded) return "bonded";
  if (facts.keysPresent) return "keys-present";
  if (facts.nodeReady) return "node-ready";
  return "not-started";
}
