#!/usr/bin/env python3
"""Public-only ROKO validator enrollment package generation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

SCHEMA = "roko.validator-enrollment.v1"
TOOL_VERSION = "1.3.0"
TESTNET_GENESIS = "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"
KEY_TYPES = ["grandpa", "babe", "imOnline", "authorityDiscovery", "mixnet", "beefy", "temporal"]
READINESS_STATES = {
    "NON_AUTHORING_NODE", "SYNCING", "SESSION_KEYS_UNRESOLVED",
    "SESSION_KEYS_MISMATCH", "SESSION_KEYS_REGISTERED", "CANDIDATE", "QUEUED",
    "ACTIVE_BABE_KEY_MISMATCH", "ACTIVE_TEMPORAL_KEY_MISMATCH",
    "ACTIVE_INITIALIZING", "CONVERGED", "AUTHORED",
}
PROHIBITED_KEY = re.compile(r"(?:secret|private|seed|mnemonic|phrase|suri|keystore|vault|openbao|token|password|cookie|approle|nodekey)", re.I)
HASH = re.compile(r"^0x[0-9a-f]{64}$", re.I)
ENCODED_KEYS = re.compile(r"^0x(?:[0-9a-f]{2}){32,1024}$", re.I)
ACCOUNT = re.compile(r"^0x[0-9a-f]{40}$", re.I)
MASK64 = (1 << 64) - 1


class EnrollmentError(RuntimeError):
    """Expected operator-facing enrollment failure."""


class RpcRejectedError(EnrollmentError):
    """A structurally valid JSON-RPC rejection, kept distinct from transport errors."""

    def __init__(self, method: str, code: int | None, message: str) -> None:
        self.method = method
        self.code = code
        self.rpc_message = message
        rendered_code = f" (code {code})" if code is not None else ""
        super().__init__(f"Local node RPC rejected {method}{rendered_code}: {message}")


def bounded_rpc_message(value: Any) -> str:
    message = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "RPC error")).strip()
    return (message or "RPC error")[:512]


def key_rpc_policy_disabled(error: RpcRejectedError) -> bool:
    """Recognize Substrate's explicit safe-policy rejection without guessing."""
    if error.code != -32601:
        return False
    return bool(re.search(r"\bunsafe\b|\bnot safe\b|\bforbidden\b|\bdenied\b|\bdisabled by.*policy\b", error.rpc_message, re.I))


def rpc_policy_status(rpc: "RpcClient") -> dict[str, Any]:
    """Non-mutating proof that key-management RPC is blocked while health remains usable."""
    health = rpc.call("system_health")
    if not isinstance(health, dict) or not isinstance(health.get("isSyncing"), bool):
        raise EnrollmentError("Safe health RPC returned a malformed system_health response")
    try:
        # This is deliberately non-mutating. Under Unsafe it returns false (or an
        # argument error after crossing the policy gate); under Safe, Substrate
        # rejects it before dispatch with the explicit unsafe-call error.
        rpc.call("author_hasSessionKeys", ["0x"])
    except RpcRejectedError as error:
        if key_rpc_policy_disabled(error):
            blocked = True
        elif error.code == -32602:
            blocked = False
        else:
            raise EnrollmentError(
                "Unable to prove Safe RPC policy: author_hasSessionKeys was rejected "
                "without the supported unsafe-policy response"
            ) from error
    else:
        blocked = False
    return {
        "schema": "roko.validator-rpc-policy.v1",
        "safeHealthRpcAvailable": True,
        "keyManagementMethodsBlocked": blocked,
        "safeForNormalOperation": blocked,
        "state": "safe-restored" if blocked else "unsafe-key-management-accessible",
        "remediation": (
            "Safe RPC policy is restored."
            if blocked
            else "Restore --rpc-methods Safe, restart the node, and repeat this check before importing the enrollment package or enabling validator mode."
        ),
    }


def _rotate_left(value: int, count: int) -> int:
    return ((value << count) | (value >> (64 - count))) & MASK64


def xxhash64(value: bytes, seed: int = 0) -> int:
    """Dependency-free xxHash64 used only to derive Substrate storage keys."""
    p1, p2, p3, p4, p5 = (11400714785074694791, 14029467366897019727, 1609587929392839161, 9650029242287828579, 2870177450012600261)
    index = 0
    if len(value) >= 32:
        lanes = [(seed + p1 + p2) & MASK64, (seed + p2) & MASK64, seed & MASK64, (seed - p1) & MASK64]
        while index <= len(value) - 32:
            for lane in range(4):
                word = int.from_bytes(value[index + lane * 8:index + lane * 8 + 8], "little")
                lanes[lane] = (_rotate_left((lanes[lane] + word * p2) & MASK64, 31) * p1) & MASK64
            index += 32
        result = sum(_rotate_left(lanes[lane], (1, 7, 12, 18)[lane]) for lane in range(4)) & MASK64
        for lane in lanes:
            mixed = (_rotate_left((lane * p2) & MASK64, 31) * p1) & MASK64
            result = ((result ^ mixed) * p1 + p4) & MASK64
    else:
        result = (seed + p5) & MASK64
    result = (result + len(value)) & MASK64
    while index <= len(value) - 8:
        word = int.from_bytes(value[index:index + 8], "little")
        mixed = (_rotate_left((word * p2) & MASK64, 31) * p1) & MASK64
        result = (_rotate_left(result ^ mixed, 27) * p1 + p4) & MASK64
        index += 8
    if index <= len(value) - 4:
        result = (_rotate_left(result ^ (int.from_bytes(value[index:index + 4], "little") * p1 & MASK64), 23) * p2 + p3) & MASK64
        index += 4
    while index < len(value):
        result = (_rotate_left(result ^ (value[index] * p5 & MASK64), 11) * p1) & MASK64
        index += 1
    result ^= result >> 33
    result = result * p2 & MASK64
    result ^= result >> 29
    result = result * p3 & MASK64
    return (result ^ (result >> 32)) & MASK64


def twox128(value: str) -> bytes:
    encoded = value.encode()
    return xxhash64(encoded, 0).to_bytes(8, "little") + xxhash64(encoded, 1).to_bytes(8, "little")


def storage_value_key(pallet: str, item: str) -> str:
    return "0x" + (twox128(pallet) + twox128(item)).hex()


def storage_map_key(pallet: str, item: str, account: str) -> str:
    if not ACCOUNT.fullmatch(account):
        raise EnrollmentError("Transition account must be a canonical 20-byte address")
    encoded = bytes.fromhex(account[2:])
    return "0x" + (twox128(pallet) + twox128(item) + xxhash64(encoded).to_bytes(8, "little") + encoded).hex()


def decode_compact_length(value: bytes) -> tuple[int, int]:
    if not value:
        raise EnrollmentError("Finalized storage returned an empty SCALE vector")
    mode = value[0] & 3
    if mode == 0:
        return value[0] >> 2, 1
    if mode == 1:
        if len(value) < 2: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
        return int.from_bytes(value[:2], "little") >> 2, 2
    if mode == 2:
        if len(value) < 4: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
        return int.from_bytes(value[:4], "little") >> 2, 4
    length = (value[0] >> 2) + 4
    if len(value) < 1 + length: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
    return int.from_bytes(value[1:1 + length], "little"), 1 + length


def decode_fixed_vector(raw: str | None, width: int) -> list[bytes]:
    if not isinstance(raw, str) or not re.fullmatch(r"0x(?:[0-9a-f]{2})*", raw, re.I):
        raise EnrollmentError("Finalized storage response is missing or malformed")
    value = bytes.fromhex(raw[2:])
    count, offset = decode_compact_length(value)
    if len(value) != offset + count * width:
        raise EnrollmentError("Finalized storage vector has an unexpected runtime shape")
    return [value[offset + index * width:offset + (index + 1) * width] for index in range(count)]


def check_transition(rpc: "RpcClient", account: str, expected_session_keys: str | None = None) -> dict[str, Any]:
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
    keys_present = isinstance(next_keys, str) and next_keys != "0x"
    keys_match = expected_session_keys is None or (keys_present and next_keys.lower() == expected_session_keys.lower())
    local_custody = expected_session_keys is None or rpc.call("author_hasSessionKeys", [expected_session_keys]) is True
    active_member = account.lower() in {entry.lower() for entry in active}
    state = "active" if active_member else "waiting" if intent and keys_present else "candidate" if intent else "bonded" if bonded else "not-started"
    return {
        "schema": "roko.validator-transition-status.v1", "account": account.lower(),
        "finalizedHash": finalized, "finalizedHeight": str(block_height(header)), "state": state,
        "bonded": bonded, "validatorIntent": intent, "sessionKeysPresent": keys_present,
        "sessionKeysMatch": keys_match, "localSessionCustody": local_custody, "active": active_member,
        "safeToEnableValidatorMode": bonded and intent and keys_present and keys_match and local_custody,
        "safeToRetireOldKeys": False,
        "retirementReason": "Retire old keys only after Agora proves replacement activation and finalized authorship.",
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(payload: dict[str, Any]) -> str:
    public_payload = {key: value for key, value in payload.items() if key != "integrity"}
    return "sha256:" + hashlib.sha256(canonical_json(public_payload).encode()).hexdigest()


def scan_prohibited(value: Any, path: str = "$") -> None:
    if isinstance(value, list):
        for index, entry in enumerate(value):
            scan_prohibited(entry, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, entry in value.items():
            if PROHIBITED_KEY.search(key) and key != "hasSessionKeys":
                raise EnrollmentError(f'{path} contains prohibited field "{key}"')
            scan_prohibited(entry, f"{path}.{key}")


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


def parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EnrollmentError("Enrollment timestamps must be ISO-8601 UTC values") from error
    if parsed.tzinfo is None:
        raise EnrollmentError("Enrollment timestamps must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def validate_enrollment(package: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    scan_prohibited(package)
    expected_top = {"schema", "enrollmentId", "generatedAt", "expiresAt", "network", "node", "session", "integrity"}
    if set(package) != expected_top:
        raise EnrollmentError("Enrollment package has missing or unsupported top-level fields")
    if package["schema"] != SCHEMA or not HASH.fullmatch(package["enrollmentId"]):
        raise EnrollmentError("Enrollment schema or identifier is invalid")
    generated = parse_utc(package["generatedAt"])
    expires = parse_utc(package["expiresAt"])
    observed_now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if expires <= generated or expires - generated > dt.timedelta(hours=24) or expires <= observed_now:
        raise EnrollmentError("Enrollment package expiry window is invalid or stale")

    network = package["network"]
    if set(network) != {"chainName", "genesisHash", "specName", "specVersion", "transactionVersion", "metadataHash"}:
        raise EnrollmentError("Enrollment network contract is incomplete")
    if not HASH.fullmatch(network["genesisHash"]) or not HASH.fullmatch(network["metadataHash"]):
        raise EnrollmentError("Enrollment network hashes are invalid")
    if not isinstance(network["specVersion"], int) or network["specVersion"] < 1:
        raise EnrollmentError("Runtime spec version is invalid")
    if not isinstance(network["transactionVersion"], int) or network["transactionVersion"] < 1:
        raise EnrollmentError("Runtime transaction version is invalid")

    node = package["node"]
    if set(node) != {"peerId", "publicAddresses", "binaryVersion", "binarySha256", "role", "rpcExposure", "health"}:
        raise EnrollmentError("Enrollment node contract is incomplete")
    if node["role"] != "non-authoring" or node["rpcExposure"] != "loopback-only":
        raise EnrollmentError("Enrollment node must be non-authoring with loopback-only RPC")
    if not HASH.fullmatch(node["binarySha256"]):
        raise EnrollmentError("Node binary digest is invalid")
    health = node["health"]
    if set(health) != {"isSyncing", "peers", "bestHeight", "finalizedHeight", "finalityAdvancing", "clockSynchronized", "p2pReachable"}:
        raise EnrollmentError("Enrollment health contract is incomplete")
    if health["isSyncing"] is not False or health["peers"] < 1:
        raise EnrollmentError("Node is syncing or has no peers")
    if not all(health[field] is True for field in ("finalityAdvancing", "clockSynchronized", "p2pReachable")):
        raise EnrollmentError("Node readiness gates are not all satisfied")
    if int(health["finalizedHeight"]) > int(health["bestHeight"]):
        raise EnrollmentError("Finalized height cannot exceed best height")

    session = package["session"]
    if set(session) != {"encodedKeys", "keyTypes", "proofMode", "proof", "hasSessionKeys"}:
        raise EnrollmentError("Enrollment session contract is incomplete")
    if not ENCODED_KEYS.fullmatch(session["encodedKeys"]) or session["keyTypes"] != KEY_TYPES:
        raise EnrollmentError("Session key tuple is invalid")
    if session["proofMode"] != "legacy-empty" or session["proof"] != "0x":
        raise EnrollmentError("ROKO currently requires explicit legacy-empty proof mode")
    if session["hasSessionKeys"] is not True:
        raise EnrollmentError("The local node does not hold the session keys")

    integrity = package["integrity"]
    if set(integrity) != {"algorithm", "digest"} or integrity["algorithm"] != "sha256":
        raise EnrollmentError("Enrollment integrity contract is invalid")
    if integrity["digest"] != canonical_digest(package):
        raise EnrollmentError("Enrollment canonical digest does not match")
    return package


class RpcClient:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout
        self.sequence = 0

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        self.sequence += 1
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params or []}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (OSError, ValueError) as error:
            raise EnrollmentError(f"Local node RPC failed for {method}: {error}") from error
        if not isinstance(payload, dict):
            raise EnrollmentError(f"Local node RPC returned malformed JSON for {method}")
        if payload.get("error"):
            error = payload["error"]
            if not isinstance(error, dict):
                raise EnrollmentError(f"Local node RPC returned a malformed error for {method}")
            code = error.get("code")
            raise RpcRejectedError(
                method,
                code if isinstance(code, int) else None,
                bounded_rpc_message(error.get("message")),
            )
        if "result" not in payload:
            raise EnrollmentError(f"Local node RPC returned no result for {method}")
        return payload["result"]


def loopback_rpc(url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port:
        raise EnrollmentError("RPC URL must include an explicit http(s) loopback host and port")
    hostname = parsed.hostname
    try:
        loopback = ipaddress.ip_address(socket.gethostbyname(hostname)).is_loopback
    except (OSError, ValueError) as error:
        raise EnrollmentError("RPC hostname could not be resolved safely") from error
    if not loopback:
        raise EnrollmentError("Validator author RPC must use a loopback address")
    return hostname, parsed.port


def listener_address_is_loopback(value: str, port: int) -> bool:
    if not value.endswith(f":{port}"):
        return False
    host = value[: -(len(str(port)) + 1)]
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    host = host.split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def listener_is_loopback(port: int) -> bool:
    executable = shutil.which("ss")
    if not executable:
        raise EnrollmentError("The 'ss' command is required to verify RPC listener exposure")
    result = subprocess.run([executable, "-ltnH"], check=True, capture_output=True, text=True)
    matched = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 4:
            continue
        local = columns[3]
        if local.endswith(f":{port}"):
            matched.append(local)
    if not matched:
        raise EnrollmentError(f"No TCP listener was found on RPC port {port}")
    unsafe = [entry for entry in matched if not listener_address_is_loopback(entry, port)]
    if unsafe:
        raise EnrollmentError(f"RPC port {port} is externally bound ({', '.join(unsafe)})")
    return True


def clock_is_synchronized() -> bool:
    timedatectl = shutil.which("timedatectl")
    if timedatectl:
        result = subprocess.run([timedatectl, "show", "-p", "NTPSynchronized", "--value"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().lower() == "yes"
    chronyc = shutil.which("chronyc")
    if chronyc:
        result = subprocess.run([chronyc, "tracking"], capture_output=True, text=True)
        if result.returncode == 0:
            leap = next((line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("Leap status")), "")
            return leap.lower() == "normal"
    raise EnrollmentError("Unable to prove host clock synchronization with timedatectl or chronyc")


def binary_identity(binary: Path) -> tuple[str, str]:
    if not binary.is_file():
        raise EnrollmentError(f"ROKO binary not found: {binary}")
    digest_state = hashlib.sha256()
    with binary.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest_state.update(chunk)
    digest = digest_state.hexdigest()
    result = subprocess.run([str(binary), "--version"], check=True, capture_output=True, text=True)
    version = (result.stdout or result.stderr).strip().splitlines()[0]
    if not version:
        raise EnrollmentError("ROKO binary returned no version")
    return version[:256], f"0x{digest}"


def block_height(header: dict[str, Any]) -> int:
    number = header.get("number")
    if not isinstance(number, str) or not number.startswith("0x"):
        raise EnrollmentError("RPC block header did not contain a hexadecimal number")
    return int(number, 16)


def metadata_digest(metadata_hex: str) -> str:
    if not isinstance(metadata_hex, str) or not re.fullmatch(r"0x(?:[0-9a-f]{2})+", metadata_hex, re.I):
        raise EnrollmentError("Runtime metadata is not valid SCALE hex")
    return "0x" + hashlib.sha256(bytes.fromhex(metadata_hex[2:])).hexdigest()


def build_enrollment(
    args: argparse.Namespace,
    rpc: RpcClient,
    *,
    observed_now: dt.datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock_probe: Callable[[], bool] = clock_is_synchronized,
    listener_probe: Callable[[int], bool] = listener_is_loopback,
    identifier: str | None = None,
) -> dict[str, Any]:
    _, port = loopback_rpc(args.rpc)
    listener_probe(port)
    if not clock_probe():
        raise EnrollmentError("Host clock is not synchronized")
    binary_version, binary_sha256 = binary_identity(Path(args.binary))

    genesis = rpc.call("chain_getBlockHash", [0])
    chain_name = rpc.call("system_chain")
    runtime = rpc.call("state_getRuntimeVersion")
    metadata = rpc.call("state_getMetadata")
    health = rpc.call("system_health")
    peer_id = rpc.call("system_localPeerId")
    listen_addresses = rpc.call("system_localListenAddresses")
    roles = rpc.call("system_nodeRoles")
    best_header = rpc.call("chain_getHeader")
    first_finalized = rpc.call("chain_getFinalizedHead")
    first_finalized_header = rpc.call("chain_getHeader", [first_finalized])
    sleep(args.observation_seconds)
    second_finalized = rpc.call("chain_getFinalizedHead")
    second_finalized_header = rpc.call("chain_getHeader", [second_finalized])

    if genesis.lower() != args.expected_genesis.lower():
        raise EnrollmentError(f"Wrong genesis: expected {args.expected_genesis}, observed {genesis}")
    if health.get("isSyncing") is not False or int(health.get("peers", 0)) < args.minimum_peers:
        raise EnrollmentError("Node must be fully synchronized with the required peer count")
    if any(str(role).lower() == "authority" for role in roles):
        raise EnrollmentError("Generate enrollment while the node is non-authoring")
    first_height = block_height(first_finalized_header)
    second_height = block_height(second_finalized_header)
    if second_height <= first_height:
        raise EnrollmentError("Finalized head did not advance during the readiness observation")
    best_height = block_height(best_header)
    if second_height > best_height:
        best_header = rpc.call("chain_getHeader")
        best_height = block_height(best_header)

    if args.session_keys:
        encoded_keys = args.session_keys
    else:
        if not args.confirm_new_keys:
            raise EnrollmentError("Creating fresh session keys requires --confirm-new-keys")
        if not args.confirm_isolated_unsafe_rpc:
            raise EnrollmentError(
                "Creating fresh session keys also requires --confirm-isolated-unsafe-rpc "
                "after proving the author RPC listener is loopback-only and is not forwarded by a proxy or tunnel"
            )
        try:
            encoded_keys = rpc.call("author_rotateKeys")
        except RpcRejectedError as error:
            if not key_rpc_policy_disabled(error):
                raise
            raise EnrollmentError(
                "Session-key generation is disabled by the node's Safe RPC policy. "
                "Either verify a previously generated public tuple with --session-keys, "
                "or use the documented roko-session-key-window helper to enable Unsafe "
                "only on the proven loopback listener and restore Safe automatically. "
                "Never expose or proxy the temporary endpoint."
            ) from error
    if not ENCODED_KEYS.fullmatch(encoded_keys):
        raise EnrollmentError("Node returned an invalid encoded session-key tuple")
    if rpc.call("author_hasSessionKeys", [encoded_keys]) is not True:
        raise EnrollmentError("Local node could not prove custody of the generated session keys")

    now = (observed_now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    expires = now + dt.timedelta(minutes=args.expires_minutes)
    public_addresses = args.public_address or list(listen_addresses)
    if not public_addresses:
        raise EnrollmentError("At least one node multiaddress is required")
    package: dict[str, Any] = {
        "schema": SCHEMA,
        "enrollmentId": identifier or f"0x{secrets.token_hex(32)}",
        "generatedAt": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "expiresAt": expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "network": {
            "chainName": chain_name,
            "genesisHash": genesis,
            "specName": runtime["specName"],
            "specVersion": int(runtime["specVersion"]),
            "transactionVersion": int(runtime["transactionVersion"]),
            "metadataHash": metadata_digest(metadata),
        },
        "node": {
            "peerId": peer_id,
            "publicAddresses": public_addresses,
            "binaryVersion": binary_version,
            "binarySha256": binary_sha256,
            "role": "non-authoring",
            "rpcExposure": "loopback-only",
            "health": {
                "isSyncing": False,
                "peers": int(health["peers"]),
                "bestHeight": str(best_height),
                "finalizedHeight": str(second_height),
                "finalityAdvancing": True,
                "clockSynchronized": True,
                "p2pReachable": True,
            },
        },
        "session": {
            "encodedKeys": encoded_keys,
            "keyTypes": KEY_TYPES,
            "proofMode": "legacy-empty",
            "proof": "0x",
            "hasSessionKeys": True,
        },
    }
    package["integrity"] = {"algorithm": "sha256", "digest": canonical_digest(package)}
    return validate_enrollment(package, now=now)


def atomic_write(path: Path, package: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(package, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def wallet_setup(rpc: "RpcClient", account: str) -> dict[str, Any]:
    """Read public chain facts for a wallet-owned browser handoff; never sign."""
    if not ACCOUNT.fullmatch(account):
        raise EnrollmentError("Wallet setup requires only a public 20-byte 0x account address")
    if rpc.call("chain_getBlockHash", [0]) != TESTNET_GENESIS:
        raise EnrollmentError("Wallet setup RPC is not the configured ROKO testnet")
    if rpc.call("eth_chainId") != "0xcc92":
        raise EnrollmentError("Wallet setup EVM chain ID does not match 52370")
    finalized = rpc.call("chain_getFinalizedHead")
    if not isinstance(finalized, str) or not HASH.fullmatch(finalized):
        raise EnrollmentError("Wallet setup requires a valid finalized block hash")
    runtime = rpc.call("state_getRuntimeVersion", [finalized])
    if not isinstance(runtime, dict) or any(
        type(runtime.get(key)) is not int or runtime[key] < 0
        for key in ("specVersion", "transactionVersion")
    ):
        raise EnrollmentError("Wallet setup runtime response is malformed")
    return {
        "schema": "roko.wallet-setup.v1",
        "toolVersion": TOOL_VERSION,
        "account": account,
        "network": {"name": "ROKO Testnet", "chainType": "substrate",
                    "rpcWss": "wss://rpc.roko.network", "chainId": 52370,
                    "genesisHash": TESTNET_GENESIS, "finalizedHash": finalized,
                    "specVersion": runtime["specVersion"],
                    "transactionVersion": runtime["transactionVersion"]},
        "signingInterface": "substrate-signPayload",
        "accountType": "ethereum-account-id20",
        "walletConnectionVerified": False,
        "metadataVerified": False,
        "packageAcceptanceVerified": False,
        "readyToSign": False,
        "links": {"agora": "https://agora.roko.network/participate/staking/",
                  "guide": "https://docs.roko.network/pages/wallets-faucet.html",
                  "talisman": "https://www.talisman.xyz/download",
                  "toolCatalog": "https://downloads.roko.network/validator-tools/current/"},
        "nextActions": [
            "Use a desktop browser with a Substrate-signing extension. Ordinary MetaMask/EVM mode cannot sign Agora staking/session calls.",
            "Talisman is the documented path with reported enrollment success; verify support for your intended account and network.",
            "If moving an account between wallets, perform any import only inside the official wallet UI. Never give this tool or an agent a private key or recovery phrase.",
            f"Verify the wallet and Agora both display the exact intended account {account}; a watch-only account cannot sign.",
            "Add ROKO as a custom Substrate network using the public WSS above. Verify genesis and current metadata in Agora; these observed RPC facts alone do not prove wallet compatibility.",
            "Only after the wallet network is verified, prepare a release-compatible enrollment package on the non-authoring node. Confirm Safe RPC restoration and Package verified in Agora before wallet actions.",
            "Compare installed tool identity with the signed catalog and actual Agora importer contract. Version labels alone do not prove package acceptance.",
            "If the package expires, use the supported refresh/reissue path without editing expiry or tuple. Expiry alone does not require new keys.",
            "Review each exact transaction and fee in the wallet; retain finalized transaction hashes. This handoff neither signs nor proves enrollment.",
        ],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Generate a public-only ROKO validator enrollment package")
    result.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    result.add_argument("--rpc", default="http://127.0.0.1:9944", help="Loopback node HTTP RPC")
    result.add_argument("--binary", default="/usr/local/bin/roko-node", help="Verified ROKO node binary")
    result.add_argument("--output", help="New or replaced public enrollment JSON path")
    result.add_argument("--expected-genesis", default=TESTNET_GENESIS)
    result.add_argument("--public-address", action="append", default=[], help="Intentional public libp2p multiaddress; repeatable")
    result.add_argument("--minimum-peers", type=int, default=1)
    result.add_argument("--observation-seconds", type=float, default=15.0)
    result.add_argument("--expires-minutes", type=int, default=30)
    result.add_argument("--check-account", help="Read finalized on-chain transition state for a canonical validator account")
    result.add_argument("--expected-session-keys", help="Public tuple expected both on chain and in this node's local keystore")
    result.add_argument("--check-rpc-policy", action="store_true", help="Non-mutating proof that key-management RPC is blocked while safe health RPC remains available")
    result.add_argument("--save-readiness", help="Write the validated redacted Safe RPC readiness result for Agora")
    result.add_argument("--wallet-setup", metavar="PUBLIC_ACCOUNT", help="Read-only wallet setup handoff; optionally save public JSON with --output. Does not generate keys or an enrollment package")
    result.add_argument("--confirm-isolated-unsafe-rpc", action="store_true", help="Confirm the temporary key-generation endpoint is loopback-only and is not forwarded by a proxy or tunnel")
    session = result.add_mutually_exclusive_group()
    session.add_argument("--confirm-new-keys", action="store_true", help="Explicitly generate a fresh session-key tuple in the local keystore")
    session.add_argument("--session-keys", help="Verify an existing public encoded key tuple in the local keystore")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.wallet_setup:
        if args.check_account or args.expected_session_keys or args.check_rpc_policy or args.save_readiness or args.confirm_new_keys or args.session_keys or args.confirm_isolated_unsafe_rpc or args.public_address:
            raise EnrollmentError("Wallet setup cannot be combined with enrollment, key generation, readiness or key RPC operations")
        loopback_rpc(args.rpc)
        handoff = wallet_setup(RpcClient(args.rpc), args.wallet_setup)
        if args.output:
            output = Path(args.output)
            if output.exists() or output.is_symlink():
                raise EnrollmentError("Wallet setup output must be a new file; do not overwrite an enrollment package")
            # Exclusive creation avoids clobbering a package if another process races us.
            with output.open("x", encoding="utf-8") as handle:
                json.dump(handoff, handle, indent=2)
                handle.write("\n")
        print(json.dumps(handoff, indent=2))
        return 0
    if args.save_readiness:
        if args.output or args.check_account or args.expected_session_keys or args.check_rpc_policy or args.confirm_new_keys or args.session_keys or args.confirm_isolated_unsafe_rpc:
            raise EnrollmentError("Readiness capture cannot create packages, rotate keys, or inspect an account")
        _, port = loopback_rpc(args.rpc)
        listener_is_loopback(port)
        report = capture_readiness(RpcClient(args.rpc))
        atomic_write(Path(args.save_readiness), report)
        print(f"Validator readiness report: {args.save_readiness}")
        print(f"Lifecycle: {report['lifecycleState']}")
        print("Validated redacted node-local result; import this file into Agora.")
        return 0
    if args.check_rpc_policy:
        if args.output or args.check_account or args.expected_session_keys or args.confirm_new_keys or args.session_keys or args.confirm_isolated_unsafe_rpc:
            raise EnrollmentError("RPC policy checks cannot create packages, rotate keys, or inspect an account")
        _, port = loopback_rpc(args.rpc)
        listener_is_loopback(port)
        status = rpc_policy_status(RpcClient(args.rpc))
        print(json.dumps(status, sort_keys=True, indent=2))
        return 0 if status["safeForNormalOperation"] else 2
    if args.check_account:
        if args.output or args.confirm_new_keys or args.session_keys or args.confirm_isolated_unsafe_rpc:
            raise EnrollmentError("Transition checks cannot create or replace enrollment output")
        status = check_transition(RpcClient(args.rpc), args.check_account, args.expected_session_keys)
        print(json.dumps(status, sort_keys=True, indent=2))
        return 0 if status["safeToEnableValidatorMode"] else 2
    if not args.output or (args.confirm_new_keys == bool(args.session_keys)):
        raise EnrollmentError("Package creation requires --output and exactly one of --confirm-new-keys or --session-keys")
    if args.minimum_peers < 1 or args.observation_seconds < 0 or not 1 <= args.expires_minutes <= 1440:
        raise EnrollmentError("Peer, observation, or expiry bounds are invalid")
    package = build_enrollment(args, RpcClient(args.rpc))
    atomic_write(Path(args.output), package)
    print(f"Validator enrollment package: {args.output}")
    print(f"Canonical digest: {package['integrity']['digest']}")
    print("Contains public node/session facts only. Import it at https://agora.roko.network/participate/staking.")
    if args.confirm_new_keys:
        print(
            "Required next step: restore --rpc-methods Safe, restart the node, and run "
            "roko-validator-enroll --rpc " + args.rpc + " --check-rpc-policy. "
            "Do not import the package or enable validator mode until that check exits 0."
        )
    return 0
