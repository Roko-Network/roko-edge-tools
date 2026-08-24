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
TESTNET_GENESIS = "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"
KEY_TYPES = ["grandpa", "babe", "imOnline", "authorityDiscovery", "mixnet", "beefy", "temporal"]
PROHIBITED_KEY = re.compile(r"(?:secret|private|seed|mnemonic|phrase|suri|keystore|vault|openbao|token|password|cookie|approle|nodekey)", re.I)
HASH = re.compile(r"^0x[0-9a-f]{64}$", re.I)
ENCODED_KEYS = re.compile(r"^0x(?:[0-9a-f]{2}){32,1024}$", re.I)


class EnrollmentError(RuntimeError):
    """Expected operator-facing enrollment failure."""


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
        if payload.get("error"):
            raise EnrollmentError(f"Local node RPC rejected {method}: {payload['error']}")
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
    unsafe = [entry for entry in matched if entry.startswith(("0.0.0.0:", "*:", "[::]:", ":::"))]
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
        encoded_keys = rpc.call("author_rotateKeys")
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Generate a public-only ROKO validator enrollment package")
    result.add_argument("--rpc", default="http://127.0.0.1:9944", help="Loopback node HTTP RPC")
    result.add_argument("--binary", default="/usr/local/bin/roko-node", help="Verified ROKO node binary")
    result.add_argument("--output", required=True, help="New or replaced public enrollment JSON path")
    result.add_argument("--expected-genesis", default=TESTNET_GENESIS)
    result.add_argument("--public-address", action="append", default=[], help="Intentional public libp2p multiaddress; repeatable")
    result.add_argument("--minimum-peers", type=int, default=1)
    result.add_argument("--observation-seconds", type=float, default=15.0)
    result.add_argument("--expires-minutes", type=int, default=30)
    session = result.add_mutually_exclusive_group(required=True)
    session.add_argument("--confirm-new-keys", action="store_true", help="Explicitly generate a fresh session-key tuple in the local keystore")
    session.add_argument("--session-keys", help="Verify an existing public encoded key tuple in the local keystore")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.minimum_peers < 1 or args.observation_seconds < 0 or not 1 <= args.expires_minutes <= 1440:
        raise EnrollmentError("Peer, observation, or expiry bounds are invalid")
    package = build_enrollment(args, RpcClient(args.rpc))
    atomic_write(Path(args.output), package)
    print(f"Validator enrollment package: {args.output}")
    print(f"Canonical digest: {package['integrity']['digest']}")
    print("Contains public node/session facts only. Import it at https://agora.roko.network/participate/staking.")
    return 0
