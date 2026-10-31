"""Command-line entry point: collect, verify and write a ROKO node system snapshot."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import socket
import sys
import uuid
from pathlib import Path

from node_snapshot import host_hardware, network_inventory, roko_install, storage_inventory, time_sync
from node_snapshot.documented_checks import evaluate_documented_checks
from node_snapshot.privacy_filter import find_sensitive_content, flag_value
from node_snapshot.probe_io import CollectionGaps, read_text, run_command
from node_snapshot.roko_rpc import RpcEndpointRefused, collect_rpc
from node_snapshot.summary_text import render_summary
from node_snapshot.utilization_sampler import sample_utilization

SCHEMA_ID = "roko.node-system-snapshot.v1"
TOOLS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICE, DEFAULT_BASE_PATH, DEFAULT_BINARY = "roko-node", "/var/lib/roko", "/usr/local/bin/roko-node"
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
EXIT_OK, EXIT_USAGE, EXIT_SENSITIVE = 0, 2, 3


def build_parser() -> argparse.ArgumentParser:
    env = os.environ
    parser = argparse.ArgumentParser(
        prog="roko-node-snapshot",
        description="Write a privacy-filtered hardware, configuration and utilization snapshot "
                    "of this ROKO node host. Runs without root; never reads keys or secrets.")
    parser.add_argument("--output", help="JSON output file (default: ./roko-node-snapshot-<UTC>.json)")
    parser.add_argument("--json", action="store_true", help="print the JSON to stdout instead of writing a file")
    parser.add_argument("--quiet", action="store_true", help="do not print the text summary")
    parser.add_argument("--sample-seconds", type=float, default=5.0, help="utilization window, 0-60 (default 5)")
    parser.add_argument("--rpc", default=env.get("ROKO_RPC_URL", "http://127.0.0.1:9944"), help="node JSON-RPC URL")
    parser.add_argument("--rpc-timeout", type=float, default=8.0, help="RPC timeout seconds")
    parser.add_argument("--no-rpc", action="store_true", help="skip node RPC queries")
    parser.add_argument("--allow-remote-rpc", action="store_true", help="permit a non-loopback --rpc URL")
    parser.add_argument("--service", default=env.get("ROKO_SERVICE"),
                        help="systemd unit (default: detected from the node process, else roko-node)")
    parser.add_argument("--base-path", default=env.get("ROKO_BASE_PATH"),
                        help="node data directory (default: native --base-path flag, else /var/lib/roko)")
    parser.add_argument("--binary", help="node binary (default: running native process, else /usr/local/bin/roko-node)")
    parser.add_argument("--process-name", default="roko-node", help="node process name")
    parser.add_argument("--no-du", action="store_true", help="skip measuring chain database size")
    parser.add_argument("--label", help="operator-chosen label, e.g. site-a-01 (letters, digits, . _ -)")
    parser.add_argument("--include-identity", action="store_true",
                        help="also record hostname and node peer ID (omitted by default)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {tools_version()}")
    return parser


def tools_version() -> str:
    return read_text(str(TOOLS_ROOT / "VERSION")) or "unknown"


def _default_binary(process: dict, process_argv: list[str]) -> str:
    executable = process_argv[0] if process_argv else ""
    if executable.startswith("/") and not process.get("inContainer"):
        return executable
    return DEFAULT_BINARY


def _collect_roko(args, gaps: CollectionGaps) -> dict:
    pid, count = roko_install.find_node_process(args.process_name)
    process, process_argv = roko_install.collect_process(pid, count, gaps)
    unit = args.service or process.get("systemdUnit") or DEFAULT_SERVICE
    service, service_argv = roko_install.collect_service(unit, gaps)
    binary = roko_install.collect_binary(args.binary or _default_binary(process, process_argv), gaps)
    enroll = run_command(["roko-validator-enroll", "--version"], timeout=10)
    return {
        "deployment": roko_install.detect_deployment(process, service_argv, binary),
        "service": service, "process": process, "binary": binary,
        "nodeFlags": roko_install.node_flags(process_argv, service_argv),
        "validatorEnrollToolVersion": enroll.strip()[:64] if enroll else None,
        "_pid": pid,
    }


def _resolve_base_path(args, roko: dict) -> str:
    if args.base_path:
        return args.base_path
    flagged = flag_value(roko["nodeFlags"]["flags"], "--base-path")
    native = roko["deployment"]["runtime"] == "native"
    if native and isinstance(flagged, str) and flagged.startswith("/") and "~" not in flagged:
        return flagged
    return DEFAULT_BASE_PATH


def collect_snapshot(args) -> dict:
    gaps = CollectionGaps()
    if os.geteuid() == 0:
        gaps.add("meta.privileges", "ran as root; root is not required")
    roko = _collect_roko(args, gaps)
    pid = roko.pop("_pid")
    base_path = _resolve_base_path(args, roko)
    network = network_inventory.collect_network()
    disk = storage_inventory.block_device_for_path(base_path)
    snapshot = {
        "schema": SCHEMA_ID,
        "snapshotId": str(uuid.uuid4()),
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toolsVersion": tools_version(),
        "label": args.label,
        "identity": {"hostname": socket.gethostname()} if args.include_identity else None,
        "host": {"os": host_hardware.collect_os(gaps), "platform": host_hardware.collect_platform(gaps),
                 "cpu": host_hardware.collect_cpu(gaps), "memory": host_hardware.collect_memory(gaps)},
        "storage": {"blockDevices": storage_inventory.collect_block_devices(gaps),
                    "dataFilesystem": storage_inventory.collect_data_filesystem(base_path, gaps),
                    "chainData": storage_inventory.collect_chain_data(base_path, not args.no_du, gaps)},
        "network": network,
        "roko": roko,
        "time": time_sync.collect_time(gaps),
        "node": {"endpointScope": None, "reachable": False} if args.no_rpc else
        collect_rpc(args.rpc, args.rpc_timeout, args.allow_remote_rpc, args.include_identity, gaps),
        "utilization": sample_utilization(args.sample_seconds, [disk] if disk else [],
                                          [i["name"] for i in network["interfaces"] if i["kind"] != "virtual"], pid),
    }
    snapshot["checks"] = evaluate_documented_checks(snapshot)
    snapshot["collectionGaps"] = gaps.items
    return snapshot


def _identity_paths(snapshot: dict) -> set:
    return {"$.identity.hostname", "$.node.peerId"} if snapshot.get("identity") else set()


def write_exclusive(path: str, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def _validate_args(args) -> str | None:
    if not 0 <= args.sample_seconds <= 60:
        return "--sample-seconds must be between 0 and 60"
    if args.label is not None and not LABEL_PATTERN.match(args.label):
        return "--label must be 1-64 characters of letters, digits, '.', '_' or '-'"
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = _validate_args(args)
    if problem:
        print(f"roko-node-snapshot: {problem}", file=sys.stderr)
        return EXIT_USAGE
    try:
        snapshot = collect_snapshot(args)
    except RpcEndpointRefused as error:
        print(f"roko-node-snapshot: {error}", file=sys.stderr)
        return EXIT_USAGE
    findings = [p for p in find_sensitive_content(snapshot) if p not in _identity_paths(snapshot)]
    if findings:
        print("roko-node-snapshot: refusing to emit; secret- or address-shaped content at: "
              + ", ".join(findings[:10]), file=sys.stderr)
        return EXIT_SENSITIVE
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.json:
        sys.stdout.write(text)
        return EXIT_OK
    stamp = snapshot["generatedAt"].replace("-", "").replace(":", "")
    output = args.output or f"roko-node-snapshot-{stamp}.json"
    try:
        write_exclusive(output, text)
    except OSError as error:
        print(f"roko-node-snapshot: cannot write {output}: {error.strerror}", file=sys.stderr)
        return EXIT_USAGE
    if not args.quiet:
        print(render_summary(snapshot, output))
    return EXIT_OK
