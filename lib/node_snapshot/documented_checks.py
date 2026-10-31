"""Evaluate a snapshot against requirements already documented in this repository."""

from __future__ import annotations

from node_snapshot.privacy_filter import flag_value

GIB = 1024 ** 3
SUPPORTED_ARCHITECTURES = ("x86_64", "aarch64", "arm64")
SUPPORTED_DISTRO_MARKERS = ("debian", "ubuntu", "fedora", "rhel", "centos")
MIN_DATA_GIB = {"full": 200, "archive": 1000}
RPC_SERVICES = ("rpc", "rpc-legacy")


def _check(check_id: str, status: str, observed, expected: str, basis: str) -> dict:
    return {"id": check_id, "status": status, "observed": str(observed)[:200],
            "expected": expected, "basis": basis}


def _platform_checks(snapshot: dict) -> list[dict]:
    os_info = snapshot["host"]["os"]
    arch = os_info.get("architecture")
    distro = f"{os_info.get('id') or ''} {os_info.get('idLike') or ''}".lower()
    return [
        _check("supported-architecture", "pass" if arch in SUPPORTED_ARCHITECTURES else "fail",
               arch, "x86_64 or aarch64", "installer/scripts/preflight.sh"),
        _check("supported-distribution",
               "pass" if any(m in distro for m in SUPPORTED_DISTRO_MARKERS) else "warn",
               distro.strip() or None, "Debian/Ubuntu or Fedora/RHEL family",
               "installer/scripts/preflight.sh"),
    ]


def _storage_check(snapshot: dict, profile: str) -> dict:
    fs, chain = snapshot["storage"]["dataFilesystem"], snapshot["storage"]["chainData"]
    minimum = MIN_DATA_GIB[profile]
    if fs.get("availableBytes") is None:
        return _check("data-volume-allowance", "unknown", None, f">= {minimum} GiB",
                      "installer/scripts/preflight.sh")
    allowance = fs["availableBytes"] + (chain.get("totalBytes") or 0)
    detail = "free+chain-data" if chain.get("totalBytes") is not None else "free-only"
    return _check("data-volume-allowance", "pass" if allowance >= minimum * GIB else "fail",
                  f"{allowance / GIB:.0f} GiB ({detail})",
                  f">= {minimum} GiB ({profile} node)", "installer/scripts/preflight.sh")


def _rpc_checks(snapshot: dict, flags: list[dict]) -> list[dict]:
    methods = flag_value(flags, "--rpc-methods")
    if isinstance(methods, str) and methods.lower() in ("safe", "unsafe"):
        methods_status = "pass" if methods.lower() == "safe" else "fail"
    else:
        methods_status = "unknown"
    exposed = [l for l in snapshot["network"]["listeners"]
               if l["service"] in RPC_SERVICES and l["bindScope"] != "loopback"]
    external_flag = any(flag_value(flags, f) for f in ("--rpc-external", "--unsafe-rpc-external"))
    rpc_listening = any(l["service"] in RPC_SERVICES for l in snapshot["network"]["listeners"])
    if exposed or external_flag:
        exposure = "fail"
    else:
        exposure = "pass" if rpc_listening else "unknown"
    return [
        _check("rpc-methods-safe", methods_status, methods, "Safe", "README.md; docs/validator-self-join.md"),
        _check("rpc-loopback-only", exposure,
               ",".join(sorted({l["bindScope"] for l in exposed})) or ("external flag" if external_flag else "loopback"),
               "RPC bound to loopback only", "README.md (Safety boundaries)"),
    ]


def _service_check(snapshot: dict) -> dict:
    service = snapshot["roko"]["service"]
    if not service.get("present"):
        return _check("service-active", "unknown", "unit not found", "active", "bin/roko-edge-doctor")
    state = service.get("activeState")
    return _check("service-active", "pass" if state == "active" else "fail", state, "active",
                  "bin/roko-edge-doctor")


def _time_check(snapshot: dict) -> dict:
    chrony = snapshot["time"].get("chrony")
    if not chrony:
        return _check("clock-sources", "unknown", "chrony not observed", ">= 2 selectable sources",
                      "docs/time-authority/verification.md")
    selectable = chrony.get("sourcesSelected", 0) + chrony.get("sourcesCombined", 0)
    healthy = chrony.get("leapStatus") == "Normal" and selectable >= 2
    return _check("clock-sources", "pass" if healthy else "warn",
                  f"leap={chrony.get('leapStatus')} selectable={selectable}",
                  "leap Normal and >= 2 selectable sources", "docs/time-authority/verification.md")


def _sync_check(snapshot: dict) -> dict:
    rpc = snapshot["node"]
    if not rpc.get("reachable"):
        return _check("node-synced", "unknown", "RPC not queried or unreachable",
                      "not syncing, peers > 0", "bin/roko-rpc-health")
    synced = rpc.get("isSyncing") is False and (rpc.get("peers") or 0) > 0
    return _check("node-synced", "pass" if synced else "warn",
                  f"syncing={rpc.get('isSyncing')} peers={rpc.get('peers')}",
                  "not syncing, peers > 0", "bin/roko-rpc-health")


def evaluate_documented_checks(snapshot: dict) -> list[dict]:
    flags = snapshot["roko"]["nodeFlags"]["flags"]
    archive = any(str(flag_value(flags, f)).startswith("archive") for f in ("--pruning", "--state-pruning"))
    profile = "archive" if archive else "full"
    return [*_platform_checks(snapshot), _storage_check(snapshot, profile),
            _service_check(snapshot), *_rpc_checks(snapshot, flags), _time_check(snapshot),
            _sync_check(snapshot)]
