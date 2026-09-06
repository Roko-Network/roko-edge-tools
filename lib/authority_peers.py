#!/usr/bin/env python3
"""Verify the signed, public active-authority transport contract."""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "roko.authority-peers.v1"
NETWORK = {
    "name": "roko-testnet-v2",
    "chainId": "52370",
    "genesisHash": "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb",
}
SIGNING_FINGERPRINT = "62297562B1C7053088F405DB0117DAAA677A5BF2"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_KEY = (
    PACKAGE_ROOT / "roko-release-signing-key.asc"
    if (PACKAGE_ROOT / "roko-release-signing-key.asc").is_file()
    else PACKAGE_ROOT / "release" / "roko-release-signing-key.asc"
)
HASH = re.compile(r"^0x[0-9a-f]{64}$")
ACCOUNT = re.compile(r"^0x[0-9a-f]{40}$")
PEER = re.compile(r"^12D3KooW[1-9A-HJ-NP-Za-km-z]{44}$")
ADDRESS = re.compile(r"^/(ip4|dns4)/([^/]+)/tcp/([0-9]{1,5})/p2p/(12D3KooW[1-9A-HJ-NP-Za-km-z]{44})$")


class AuthorityPeerError(RuntimeError):
    """Expected operator-facing manifest failure."""


def parse_utc(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise AuthorityPeerError("Authority manifest timestamp is malformed")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AuthorityPeerError("Authority manifest timestamp is malformed") from error
    if parsed.tzinfo is None:
        raise AuthorityPeerError("Authority manifest timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def public_address(value: str, expected_peer: str) -> bool:
    match = ADDRESS.fullmatch(value)
    if not match or match.group(4) != expected_peer:
        return False
    port = int(match.group(3))
    if not 1 <= port <= 65535:
        return False
    try:
        candidates = [ipaddress.ip_address(match.group(2))] if match.group(1) == "ip4" else [
            ipaddress.ip_address(entry[4][0])
            for entry in socket.getaddrinfo(match.group(2), port, socket.AF_INET, socket.SOCK_STREAM)
        ]
    except (OSError, ValueError):
        return False
    return bool(candidates) and all(address.is_global for address in candidates)


def validate_manifest(value: Any, now: dt.datetime | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "network", "generatedAt", "expiresAt", "finalized",
        "minimumMappedPeers", "authorities",
    }:
        raise AuthorityPeerError("Authority manifest has missing or unsupported fields")
    if value["schema"] != SCHEMA or value["network"] != NETWORK:
        raise AuthorityPeerError("Authority manifest targets the wrong network")
    observed = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    generated = parse_utc(value["generatedAt"])
    expires = parse_utc(value["expiresAt"])
    if generated > observed + dt.timedelta(minutes=5):
        raise AuthorityPeerError("Authority manifest was generated in the future")
    if expires <= observed or expires <= generated or expires - generated > dt.timedelta(days=14):
        raise AuthorityPeerError("Authority manifest is expired or has an invalid validity window")
    finalized = value["finalized"]
    if not isinstance(finalized, dict) or set(finalized) != {"blockNumber", "blockHash", "sessionIndex"}:
        raise AuthorityPeerError("Authority manifest finalized evidence is malformed")
    if not isinstance(finalized["blockNumber"], int) or isinstance(finalized["blockNumber"], bool) or finalized["blockNumber"] < 1:
        raise AuthorityPeerError("Authority manifest finalized block number is malformed")
    if not isinstance(finalized["sessionIndex"], int) or isinstance(finalized["sessionIndex"], bool) or finalized["sessionIndex"] < 0:
        raise AuthorityPeerError("Authority manifest session index is malformed")
    if not isinstance(finalized["blockHash"], str) or not HASH.fullmatch(finalized["blockHash"]):
        raise AuthorityPeerError("Authority manifest finalized block hash is malformed")
    if value["minimumMappedPeers"] != 2:
        raise AuthorityPeerError("Authority manifest may not lower the two-mapped-peer gate")
    authorities = value["authorities"]
    if not isinstance(authorities, list) or not 2 <= len(authorities) <= 32:
        raise AuthorityPeerError("Authority manifest must publish at least two active authorities")
    accounts: set[str] = set()
    peers: set[str] = set()
    addresses: set[str] = set()
    for authority in authorities:
        if not isinstance(authority, dict) or set(authority) != {"account", "peerId", "addresses"}:
            raise AuthorityPeerError("Authority manifest entry is malformed")
        account, peer = authority["account"], authority["peerId"]
        if not isinstance(account, str) or not ACCOUNT.fullmatch(account):
            raise AuthorityPeerError("Authority account is malformed")
        if not isinstance(peer, str) or not PEER.fullmatch(peer):
            raise AuthorityPeerError("Authority peer ID is malformed")
        entries = authority["addresses"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 4:
            raise AuthorityPeerError("Authority address list is malformed")
        if account in accounts or peer in peers:
            raise AuthorityPeerError("Authority accounts and peer IDs must be unique")
        accounts.add(account); peers.add(peer)
        for address in entries:
            if not isinstance(address, str) or not public_address(address, peer):
                raise AuthorityPeerError("Authority address is private, unresolved, or mismatched")
            if address in addresses:
                raise AuthorityPeerError("Authority addresses must be unique")
            addresses.add(address)
    return value


def verify_signature(manifest: Path, signature: Path, public_key: Path) -> None:
    for path in (manifest, signature, public_key):
        if not path.is_file():
            raise AuthorityPeerError(f"Required verification input is missing: {path}")
    with tempfile.TemporaryDirectory(prefix="roko-authority-gpg-") as home:
        os.chmod(home, 0o700)
        shown = subprocess.run(
            ["gpg", "--batch", "--homedir", home, "--with-colons", "--import-options", "show-only", "--import", str(public_key)],
            check=True, capture_output=True, text=True,
        )
        fingerprints = [line.split(":")[9].upper() for line in shown.stdout.splitlines() if line.startswith("fpr:")]
        if not fingerprints or fingerprints[0] != SIGNING_FINGERPRINT:
            raise AuthorityPeerError("Authority manifest public signing key has the wrong fingerprint")
        subprocess.run(["gpg", "--batch", "--homedir", home, "--import", str(public_key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        verified = subprocess.run(
            ["gpg", "--batch", "--status-fd", "1", "--homedir", home, "--verify", str(signature), str(manifest)],
            capture_output=True, text=True,
        )
        if verified.returncode != 0 or f"VALIDSIG {SIGNING_FINGERPRINT}" not in verified.stdout:
            raise AuthorityPeerError("Authority manifest detached signature did not verify")


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a signed ROKO active-authority peer manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument(
        "--public-key",
        default=str(DEFAULT_PUBLIC_KEY),
        help="Pinned ROKO release public key (defaults to the signed tool package)",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    manifest = Path(args.manifest)
    verify_signature(manifest, Path(args.signature), Path(args.public_key))
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AuthorityPeerError("Authority manifest is not valid JSON") from error
    atomic_write(Path(args.output), validate_manifest(value))
    print(f"Verified active-authority manifest: {args.output}")
    print(f"Authorities: {len(value['authorities'])}; minimum mapped peers: {value['minimumMappedPeers']}")
    return 0
