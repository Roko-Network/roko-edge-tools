"""Versioned, public, tamper-evident transition evidence."""
import hashlib
import json
import re
from typing import Any

from validator_contract import HASH, EnrollmentError, scan_prohibited

SOURCE = re.compile(r"^[0-9a-f]{40}$", re.I)


def digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "integrity"}
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def verify_receipt(value: dict[str, Any]) -> dict[str, Any]:
    scan_prohibited(value)
    if value.get("schema") != "roko.validator-transition-status.v2" or value.get("integrity") != {
        "algorithm": "sha256", "digest": digest(value)
    }:
        raise EnrollmentError("Transition receipt schema or canonical digest is invalid")
    return value


def transition_receipt(status: dict[str, Any], rpc: Any, readiness: dict[str, Any],
                       roles: list[str], submitted: str | None, next_keys: str | None, active: list[str],
                       qualification: dict[str, Any] | None) -> dict[str, Any]:
    # The Safe readiness RPC exposes queuedKeysMatch, not the raw queued set.
    # Preserve that limitation rather than invent a queued-account RPC field.
    status["evidence"] = {
        "submittedPublicTuple": submitted,
        "finalizedNextKeys": next_keys if status["sessionKeysPresent"] else None,
        "queuedKeysMatch": readiness["queuedKeysMatch"],
        "queuedSetEvidence": "Safe readiness RPC queuedKeysMatch (not raw queued set)",
        "activeSet": active,
        "activeBabeAuthorityIndex": readiness["activeBabeAuthorityIndex"],
        "activeTemporalAuthorityIndex": readiness["activeTemporalAuthorityIndex"],
        "producerAuthorityIndex": readiness["producerAuthorityIndex"],
        "expectedTemporalPublic": readiness["expectedTemporalPublic"],
        "observedTemporalPublic": readiness["observedTemporalPublic"],
        "sessionKeys": readiness["sessionKeys"],
        "sessionIndex": readiness["sessionIndex"],
        "mappedTemporalPeers": readiness["mappedTemporalPeers"],
        "genericP2pPeers": readiness["genericP2pPeers"],
        "systemNodeRoles": roles,
        "authorshipProof": readiness["authorshipProof"],
    }
    status["qualification"] = qualification
    status["observedIdentity"] = None
    if qualification is None:
        status["failedStages"].append("Qualification identity missing: provide reviewed source, image/native, genesis, runtime and binary identities before handoff.")
    else:
        required = {"sourceCommit", "imageDigest", "binarySha256", "genesisHash", "specName", "specVersion", "metadataHash"}
        scan_prohibited(qualification)
        if (set(qualification) != required or not isinstance(qualification.get("sourceCommit"), str)
                or not SOURCE.fullmatch(qualification["sourceCommit"])
                or qualification.get("imageDigest") is not None and (not isinstance(qualification["imageDigest"], str)
                or not HASH.fullmatch(qualification["imageDigest"]))
                or not all(isinstance(qualification.get(field), str) and HASH.fullmatch(qualification[field])
                           for field in ("binarySha256", "genesisHash", "metadataHash"))
                or not isinstance(qualification.get("specName"), str)
                or type(qualification.get("specVersion")) is not int):
            raise EnrollmentError("Qualification public identity contract is malformed")
        genesis = rpc.call("chain_getBlockHash", [0])
        runtime = rpc.call("state_getRuntimeVersion")
        metadata = rpc.call("state_getMetadata")
        metadata_hash = "0x" + hashlib.sha256(bytes.fromhex(metadata[2:])).hexdigest() if isinstance(metadata, str) and re.fullmatch(r"0x(?:[0-9a-f]{2})+", metadata, re.I) else None
        status["observedIdentity"] = {
            "genesisHash": genesis, "specName": runtime.get("specName"),
            "specVersion": runtime.get("specVersion"), "metadataHash": metadata_hash,
        }
        if (genesis != qualification["genesisHash"] or runtime.get("specName") != qualification["specName"]
                or runtime.get("specVersion") != qualification["specVersion"]
                or metadata_hash != qualification["metadataHash"]):
            status["failedStages"].append("Qualification identity mismatch: stop and requalify the installed genesis and runtime before handoff.")
    status["safeToEnableValidatorMode"] = not status["failedStages"]
    status["safeToAuthor"] = status["safeToEnableValidatorMode"] and status["active"]
    status["authorshipProven"] = status["safeToAuthor"] and status["authorshipProven"]
    status["integrity"] = {"algorithm": "sha256", "digest": digest(status)}
    return verify_receipt(status)
