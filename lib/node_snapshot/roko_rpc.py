"""Query a local ROKO node over Safe JSON-RPC for public sync, version and mesh state."""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

from node_snapshot.probe_io import CollectionGaps

SAFE_METHODS = ("system_name", "system_version", "system_chain", "system_health", "system_nodeRoles",
                "system_syncState", "chain_getFinalizedHead", "state_getRuntimeVersion",
                "temporal_getMeshState")
IDENTITY_METHODS = ("system_localPeerId",)


class RpcEndpointRefused(ValueError):
    """Raised when a non-loopback RPC endpoint is used without explicit opt-in."""


def endpoint_scope(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "localhost":
        return "loopback"
    try:
        return "loopback" if ipaddress.ip_address(host).is_loopback else "remote"
    except ValueError:
        return "remote"


def _post(url: str, body, timeout: float):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json",
                                              "user-agent": "roko-edge-tools/node-snapshot"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(4 * 1024 * 1024).decode())


def _batch(url: str, methods: tuple, timeout: float) -> dict:
    body = [{"jsonrpc": "2.0", "id": index, "method": method, "params": []}
            for index, method in enumerate(methods)]
    replies = _post(url, body, timeout)
    by_id = {item.get("id"): item for item in replies if isinstance(item, dict)}
    return {method: by_id.get(index, {}) for index, method in enumerate(methods)}


def _hex_int(value) -> int | None:
    try:
        return int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None


def _finalized_number(url: str, finalized_hash, timeout: float) -> int | None:
    if not isinstance(finalized_hash, str):
        return None
    reply = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "chain_getHeader",
                        "params": [finalized_hash]}, timeout)
    return _hex_int((reply.get("result") or {}).get("number"))


def _summarize(results: dict, finalized_number: int | None) -> dict:
    def result(method):
        return results.get(method, {}).get("result")
    health, sync = result("system_health") or {}, result("system_syncState") or {}
    runtime, mesh = result("state_getRuntimeVersion") or {}, result("temporal_getMeshState") or {}
    return {
        "software": result("system_name"),
        "version": result("system_version"),
        "chain": result("system_chain"),
        "roles": result("system_nodeRoles"),
        "peers": health.get("peers"),
        "isSyncing": health.get("isSyncing"),
        "currentBlock": _hex_int(sync.get("currentBlock")),
        "highestBlock": _hex_int(sync.get("highestBlock")),
        "finalizedBlock": finalized_number,
        "specName": runtime.get("specName"),
        "specVersion": runtime.get("specVersion"),
        "meshPeerCount": mesh.get("peerCount"),
        "meshTimeQuality": mesh.get("timeQuality"),
        "meshConvergenceState": mesh.get("convergenceState"),
        "unavailableMethods": sorted(m for m, reply in results.items() if "result" not in reply),
    }


def collect_rpc(url: str, timeout: float, allow_remote: bool, include_identity: bool,
                gaps: CollectionGaps) -> dict:
    scope = endpoint_scope(url)
    if scope != "loopback" and not allow_remote:
        raise RpcEndpointRefused("refusing non-loopback RPC; pass --allow-remote-rpc to query it")
    methods = SAFE_METHODS + (IDENTITY_METHODS if include_identity else ())
    try:
        results = _batch(url, methods, timeout)
        finalized = _finalized_number(url, results["chain_getFinalizedHead"].get("result"), timeout)
    except (urllib.error.URLError, OSError, ValueError, AttributeError) as error:
        gaps.add("node.rpc", f"RPC unreachable ({type(error).__name__})")
        return {"endpointScope": scope, "reachable": False}
    summary = {"endpointScope": scope, "reachable": True, **_summarize(results, finalized)}
    if include_identity:
        summary["peerId"] = results["system_localPeerId"].get("result")
    return summary
