"""Safe RPC readiness validation and finalized transition checks."""
import re
from typing import Any
from validator_contract import (ACCOUNT, ENCODED_KEYS, HASH, KEY_TYPES, READINESS_STATES,
                                EnrollmentError, RpcRejectedError, scan_prohibited)
from validator_storage import storage_value_key, storage_map_key, decode_fixed_vector
from validator_receipt import transition_receipt

def key_rpc_policy_disabled(error: RpcRejectedError) -> bool:
    """Recognize Substrate's explicit safe-policy rejection without guessing."""
    return error.code in {1040, -32601} and (
        error.rpc_message.strip().rstrip(".").lower()
        == "rpc call is unsafe to be called externally"
    )


def transition_local_custody(rpc: "RpcClient", account: str, encoded_keys: str) -> bool:
    """Prove custody without opening an Unsafe RPC window on a running node."""
    try:
        return rpc.call("author_hasSessionKeys", [encoded_keys]) is True
    except RpcRejectedError as error:
        if not key_rpc_policy_disabled(error):
            raise
    report = capture_readiness(rpc)
    candidate = report["candidateAccount"]
    if candidate is not None and candidate.lower() != account.lower():
        return False
    # Readiness can precede account discovery: its observed public keys still
    # prove custody, while check_transition separately binds the entire tuple
    # to this account's finalized Session.NextKeys. Never trust aggregate flags
    # or a tuple belonging to some other candidate.
    offset = 2
    for entry, width in zip(report["sessionKeys"], (32, 32, 32, 32, 32, 33, 33)):
        public = "0x" + encoded_keys[offset:offset + width * 2].lower()
        offset += width * 2
        if public not in {value.lower() for value in entry["observedPublic"]}:
            return False
        expected = entry["expectedPublic"]
        if expected is not None and (expected.lower() != public or not entry["matchesExpected"]):
            return False
    return True


def check_transition(rpc: "RpcClient", account: str, expected_session_keys: str | None = None,
                     qualification: dict[str, Any] | None = None) -> dict[str, Any]:
    if not ACCOUNT.fullmatch(account):
        raise EnrollmentError("Transition account must be a canonical 20-byte address")
    if expected_session_keys is not None and not ENCODED_KEYS.fullmatch(expected_session_keys):
        raise EnrollmentError("Expected public session-key tuple is malformed")
    finalized = rpc.call("chain_getFinalizedHead")
    header = rpc.call("chain_getHeader", [finalized])
    active_raw = rpc.call("state_getStorage", [storage_value_key("Session", "Validators"), finalized])
    active = ["0x" + entry.hex() for entry in decode_fixed_vector(active_raw, 20)]
    bonded = rpc.call("state_getStorage", [storage_map_key("Staking", "Bonded", account), finalized]) is not None
    intent = rpc.call("state_getStorage", [storage_map_key("Staking", "Validators", account), finalized]) is not None
    next_keys = rpc.call("state_getStorage", [storage_map_key("Session", "NextKeys", account), finalized])
    keys_present = isinstance(next_keys, str) and bool(ENCODED_KEYS.fullmatch(next_keys)) and len(next_keys) == 454
    keys_match = expected_session_keys is not None and keys_present and next_keys.lower() == expected_session_keys.lower()
    local_custody = expected_session_keys is not None and transition_local_custody(rpc, account, expected_session_keys)
    active_member = account.lower() in {entry.lower() for entry in active}
    report = capture_readiness(rpc)
    roles = rpc.call("system_nodeRoles")
    if not isinstance(roles, list) or not all(role in {"Authority", "Full", "Light", "Sentry"} for role in roles):
        raise EnrollmentError("system_nodeRoles returned malformed roles")
    failures = []
    if not bonded or not intent:
        failures.append("Complete finalized bond and validator candidacy first.")
    if not keys_present or not keys_match or not local_custody:
        failures.append("Session tuple mismatch: match all seven locally held public keys to finalized session.nextKeys before handoff.")
    registered_temporal = "0x" + next_keys[-66:].lower() if keys_present else None
    if (registered_temporal is not None and
            (report["expectedTemporalPublic"] is None or
             report["expectedTemporalPublic"].lower() != registered_temporal or
             registered_temporal not in [value.lower() for value in report["observedTemporalPublic"]])):
        failures.append("Temporal public key mismatch: registered temporal key differs from local reported temporal key; restore the registered public tuple on this node or submit a reviewed rotation.")
    if report["candidateAccount"] is not None and report["candidateAccount"].lower() != account.lower():
        failures.append("Select the candidate account reported by the local node.")
    if report["majorSyncing"] is not False or report["validatorRoleConfigured"] is not True:
        failures.append("Finish syncing and configure the validator role before handoff; system_nodeRoles alone is not readiness.")
    if report["minimumTemporalSources"] < 2:
        failures.append("Time-source policy requires at least two mapped authorities; restore --timesync-min-sources 2 unless a separately reviewed protocol policy authorizes a different profile.")
    if report["mappedTemporalPeers"] < max(2, report["minimumTemporalSources"]):
        failures.append("Connect at least two mapped active-authority temporal peers; ordinary P2P peers do not count.")
    if not report["nextKeysMatch"] or not report["candidateIntent"] or report["matchedSessionKeyCount"] != 7:
        failures.append("Resolve the Safe readiness RPC's candidacy and seven-key nextKeys mismatch.")
    if keys_present:
        offset = 2
        for entry, width in zip(report["sessionKeys"], (32, 32, 32, 32, 32, 33, 33)):
            public = "0x" + next_keys[offset:offset + width * 2].lower()
            offset += width * 2
            if (entry["expectedPublic"] is None or entry["expectedPublic"].lower() != public
                    or not entry["matchesExpected"] or public not in
                    [value.lower() for value in entry["observedPublic"]]):
                failures.append(f"Public {entry['name']} key mismatch: restore the registered tuple locally or submit a reviewed rotation.")
    if active_member and not (report["activeSessionMatch"] and report["activeBabeAuthorityIndex"] is not None
                              and report["activeBabeAuthorityIndex"] == report["activeTemporalAuthorityIndex"]
                              and report["producerAuthorityIndex"] == report["activeBabeAuthorityIndex"]):
        failures.append("Active authority mapping mismatch: wait for local BABE, temporal and producer mappings to agree with the active session.")
    if active_member and (report["convergenceState"] != "Converged" or not report["readyToAuthor"]):
        failures.append("Time quality not converged: restore mapped active-authority peers and wait for Safe RPC authoring readiness.")
    proof = report["authorshipProof"]
    authored = (active_member and proof is not None and
                proof["authorityIndex"] == report["producerAuthorityIndex"] and
                proof["blockNumber"] <= block_height(header) and
                rpc.call("chain_getBlockHash", [proof["blockNumber"]]) == proof["blockHash"])
    if active_member and not authored:
        failures.append("Finalized authorship missing or mismatched: wait for a canonical finalized block authored by the expected authority.")
    state = "active" if active_member else "waiting" if intent and keys_present else "candidate" if intent else "bonded" if bonded else "not-started"
    status = {
        "schema": "roko.validator-transition-status.v2", "account": account.lower(),
        "finalizedHash": finalized, "finalizedHeight": str(block_height(header)), "state": state,
        "bonded": bonded, "validatorIntent": intent, "sessionKeysPresent": keys_present,
        "sessionKeysMatch": keys_match, "localSessionCustody": local_custody, "active": active_member,
        "safeToEnableValidatorMode": not failures,
        "mappedTemporalPeers": report["mappedTemporalPeers"], "genericP2pPeers": report["genericP2pPeers"],
        "safeToAuthor": not failures and active_member and report["readyToAuthor"],
        "authorshipProven": not failures and authored,
        "failedStages": failures,
        "safeToRetireOldKeys": False,
        "retirementReason": "Retire old keys only after Agora proves replacement activation and finalized authorship.",
    }
    return transition_receipt(status, rpc, report, roles, expected_session_keys, next_keys, active, qualification)


def reject_sensitive_text(value: str) -> None:
    if re.search(r"(?:/home/|/root/|/etc/|/var/lib/|password\s*[:=]|token\s*[:=]|secret\s*[:=])", value, re.I):
        raise EnrollmentError("Validator readiness contains unsafe explanatory text")


def validate_readiness(report: Any) -> dict[str, Any]:
    """Validate the redacted node RPC result before handing it to Agora."""
    if not isinstance(report, dict):
        raise EnrollmentError("Validator readiness RPC returned a non-object result")
    scan_prohibited(report)
    required = {
        "lifecycleState", "validatorRoleConfigured", "majorSyncing",
        "genericP2pPeers", "finalizedBlock", "sessionIndex", "candidateAccount",
        "matchedSessionKeyCount", "requiredSessionKeyCount", "sessionKeys",
        "candidateIntent", "nextKeysMatch", "queuedKeysMatch", "activeSessionMatch",
        "activeBabeAuthorityIndex", "activeTemporalAuthorityIndex",
        "producerAuthorityIndex", "expectedTemporalPublic", "observedTemporalPublic",
        "convergenceState", "minimumTemporalSources", "temporalTransportPeers",
        "mappedTemporalPeers", "contributingTemporalPeers", "peerExclusions",
        "readyToAuthor", "authorshipProof", "remediation",
    }
    if set(report) != required:
        raise EnrollmentError("Validator readiness result has missing or unsupported fields")
    if report["lifecycleState"] not in READINESS_STATES:
        raise EnrollmentError("Validator readiness lifecycle state is unsupported")
    optional_ints = ("genericP2pPeers", "activeBabeAuthorityIndex", "activeTemporalAuthorityIndex", "producerAuthorityIndex")
    for field in optional_ints:
        if report[field] is not None and (not isinstance(report[field], int) or isinstance(report[field], bool) or report[field] < 0):
            raise EnrollmentError(f"Validator readiness field {field} is malformed")
    required_ints = (
        "finalizedBlock", "sessionIndex", "matchedSessionKeyCount",
        "requiredSessionKeyCount", "minimumTemporalSources", "temporalTransportPeers",
        "mappedTemporalPeers", "contributingTemporalPeers",
    )
    for field in required_ints:
        if not isinstance(report[field], int) or isinstance(report[field], bool) or report[field] < 0:
            raise EnrollmentError(f"Validator readiness field {field} is malformed")
    if report["requiredSessionKeyCount"] != 7 or not 0 <= report["matchedSessionKeyCount"] <= 7:
        raise EnrollmentError("Validator readiness seven-key count is invalid")
    for field in ("validatorRoleConfigured", "candidateIntent", "nextKeysMatch", "queuedKeysMatch", "activeSessionMatch", "readyToAuthor"):
        if not isinstance(report[field], bool):
            raise EnrollmentError(f"Validator readiness field {field} is malformed")
    if report["majorSyncing"] is not None and not isinstance(report["majorSyncing"], bool):
        raise EnrollmentError("Validator readiness field majorSyncing is malformed")
    if report["candidateAccount"] is not None and not ACCOUNT.fullmatch(report["candidateAccount"]):
        raise EnrollmentError("Validator readiness candidate account is malformed")
    public_key = re.compile(r"^0x(?:[0-9a-f]{64}|[0-9a-f]{66})$", re.I)
    if report["expectedTemporalPublic"] is not None and not public_key.fullmatch(report["expectedTemporalPublic"]):
        raise EnrollmentError("Validator readiness expected temporal public key is malformed")
    observed_temporal = report["observedTemporalPublic"]
    if not isinstance(observed_temporal, list) or len(observed_temporal) > 64 or not all(isinstance(value, str) and public_key.fullmatch(value) for value in observed_temporal):
        raise EnrollmentError("Validator readiness observed temporal public keys are malformed")
    session_keys = report["sessionKeys"]
    if not isinstance(session_keys, list) or len(session_keys) != 7:
        raise EnrollmentError("Validator readiness must contain exactly seven session-key records")
    expected_crypto = dict(zip(KEY_TYPES, ["ed25519", "sr25519", "sr25519", "sr25519", "sr25519", "ecdsa", "ecdsa"]))
    for index, entry in enumerate(session_keys):
        if not isinstance(entry, dict) or set(entry) != {"name", "keyType", "cryptography", "expectedPublic", "observedPublic", "matchesExpected"}:
            raise EnrollmentError("Validator readiness session-key record is malformed")
        name = KEY_TYPES[index]
        if entry["name"] != name or entry["cryptography"] != expected_crypto[name]:
            raise EnrollmentError("Validator readiness session-key ordering or cryptography is invalid")
        if not isinstance(entry["keyType"], str) or len(entry["keyType"]) != 4:
            raise EnrollmentError("Validator readiness session key type is malformed")
        if entry["expectedPublic"] is not None and not public_key.fullmatch(entry["expectedPublic"]):
            raise EnrollmentError("Validator readiness expected session public key is malformed")
        observed = entry["observedPublic"]
        if not isinstance(observed, list) or len(observed) > 64 or not all(isinstance(value, str) and public_key.fullmatch(value) for value in observed):
            raise EnrollmentError("Validator readiness observed session public keys are malformed")
        if not isinstance(entry["matchesExpected"], bool):
            raise EnrollmentError("Validator readiness session-key match flag is malformed")
    exclusions = report["peerExclusions"]
    if not isinstance(exclusions, list) or len(exclusions) > 64:
        raise EnrollmentError("Validator readiness peer exclusions are malformed")
    for entry in exclusions:
        if not isinstance(entry, dict) or set(entry) != {"reason", "count", "explanation"}:
            raise EnrollmentError("Validator readiness peer exclusion is malformed")
        if not isinstance(entry["reason"], str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", entry["reason"]):
            raise EnrollmentError("Validator readiness peer exclusion reason is malformed")
        if not isinstance(entry["count"], int) or isinstance(entry["count"], bool) or entry["count"] < 0:
            raise EnrollmentError("Validator readiness peer exclusion count is malformed")
        if not isinstance(entry["explanation"], str) or not 1 <= len(entry["explanation"]) <= 1024:
            raise EnrollmentError("Validator readiness peer exclusion explanation is malformed")
        reject_sensitive_text(entry["explanation"])
    proof = report["authorshipProof"]
    if proof is not None:
        if not isinstance(proof, dict) or set(proof) != {"blockNumber", "blockHash", "authorityIndex"}:
            raise EnrollmentError("Validator readiness authorship proof is malformed")
        if not isinstance(proof["blockNumber"], int) or proof["blockNumber"] < 0:
            raise EnrollmentError("Validator readiness authorship block is malformed")
        if not HASH.fullmatch(proof["blockHash"]):
            raise EnrollmentError("Validator readiness authorship hash is malformed")
        if not isinstance(proof["authorityIndex"], int) or proof["authorityIndex"] < 0:
            raise EnrollmentError("Validator readiness authorship authority is malformed")
    if not isinstance(report["convergenceState"], str) or not 1 <= len(report["convergenceState"]) <= 64:
        raise EnrollmentError("Validator readiness convergence state is malformed")
    if not isinstance(report["remediation"], str) or not 1 <= len(report["remediation"]) <= 2048:
        raise EnrollmentError("Validator readiness remediation is malformed")
    reject_sensitive_text(report["remediation"])
    return report


def capture_readiness(rpc: "RpcClient") -> dict[str, Any]:
    try:
        return validate_readiness(rpc.call("temporal_getValidatorReadiness"))
    except RpcRejectedError as error:
        if error.code == -32601:
            raise EnrollmentError(
                "Installed node does not provide temporal_getValidatorReadiness. "
                "Install the current checksum-verified ROKO testnet release, restart, "
                "and confirm rpc_methods lists the Safe readiness method."
            ) from error
        raise


def block_height(header: dict[str, Any]) -> int:
    number = header.get("number")
    if not isinstance(number, str) or not number.startswith("0x"):
        raise EnrollmentError("RPC block header did not contain a hexadecimal number")
    return int(number, 16)


