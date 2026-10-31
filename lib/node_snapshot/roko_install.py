"""Collect the ROKO node service, running process, binary and deployment type without root."""

from __future__ import annotations

import hashlib
import os
import re
import time

from node_snapshot.privacy_filter import sanitize_node_arguments, scrub_path
from node_snapshot.probe_io import CollectionGaps, parse_key_values, read_text, run_command, to_int

SERVICE_PROPERTIES = ("LoadState", "ActiveState", "SubState", "UnitFileState", "NRestarts",
                      "ExecMainStartTimestampMonotonic", "MemoryCurrent", "CPUUsageNSec",
                      "TasksCurrent", "LimitNOFILE", "Restart", "ExecStart")
UNSET_MARKERS = ("", "[not set]", "infinity", "18446744073709551615")
IMAGE_ENV_FILE = "/etc/roko/node-image.env"


def _clean_number(value: str | None) -> int | None:
    return None if value in UNSET_MARKERS or value is None else to_int(value)


def _exec_start_argv(exec_start: str) -> list[str]:
    match = re.search(r"argv\[\]=(.*?) ;", exec_start or "")
    return match.group(1).split() if match else []


def collect_service(service: str, gaps: CollectionGaps) -> tuple[dict, list[str]]:
    raw = run_command(["systemctl", "show", service, "--no-pager",
                       "-p", ",".join(SERVICE_PROPERTIES)])
    if raw is None:
        gaps.add("roko.service", "systemctl unavailable")
        return {"name": service, "present": None}, []
    props = parse_key_values(raw)
    started_us = _clean_number(props.get("ExecMainStartTimestampMonotonic"))
    uptime = time.clock_gettime(time.CLOCK_MONOTONIC) if hasattr(time, "clock_gettime") else None
    service_info = {
        "name": service,
        "present": props.get("LoadState") == "loaded",
        "activeState": props.get("ActiveState"),
        "subState": props.get("SubState"),
        "unitFileState": props.get("UnitFileState"),
        "restartPolicy": props.get("Restart"),
        "restartCount": _clean_number(props.get("NRestarts")),
        "activeSeconds": int(uptime - started_us / 1e6) if started_us and uptime else None,
        "memoryCurrentBytes": _clean_number(props.get("MemoryCurrent")),
        "cpuUsageSeconds": round(_clean_number(props.get("CPUUsageNSec")) / 1e9, 1)
        if _clean_number(props.get("CPUUsageNSec")) is not None else None,
        "tasksCurrent": _clean_number(props.get("TasksCurrent")),
        "limitNofile": _clean_number(props.get("LimitNOFILE")),
    }
    return service_info, _exec_start_argv(props.get("ExecStart", ""))


def find_node_process(process_name: str) -> tuple[int | None, int]:
    matches = []
    for entry in os.listdir("/proc"):
        if entry.isdigit() and read_text(f"/proc/{entry}/comm") == process_name[:15]:
            matches.append(int(entry))
    return (min(matches) if matches else None), len(matches)


def _status_fields(pid: int) -> dict:
    values = {}
    for line in (read_text(f"/proc/{pid}/status") or "").splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "VmHWM", "Threads"):
            number = to_int(value.split()[0]) if value.split() else None
            values[key] = number * 1024 if number is not None and key != "Threads" else number
    return values


def _open_files_limit(pid: int) -> int | None:
    for line in (read_text(f"/proc/{pid}/limits") or "").splitlines():
        if line.startswith("Max open files"):
            return to_int(line.split()[3])
    return None


def collect_process(pid: int | None, count: int, gaps: CollectionGaps) -> tuple[dict, list[str]]:
    if pid is None:
        return {"running": False, "matchingProcesses": 0}, []
    status = _status_fields(pid)
    stat = read_text(f"/proc/{pid}/stat") or ""
    start_ticks = to_int(stat.rsplit(")", 1)[-1].split()[19]) if ")" in stat else None
    uptime_text = read_text("/proc/uptime")
    try:
        open_fds = len(os.listdir(f"/proc/{pid}/fd"))
    except OSError:
        open_fds = None
        gaps.add("roko.process.openFiles", "fd count needs the node user or root")
    cgroup = read_text(f"/proc/{pid}/cgroup") or ""
    argv = (read_text(f"/proc/{pid}/cmdline") or "").split()
    unit = re.search(r"/([A-Za-z0-9@._-]+\.service)\s*$", cgroup)
    process_info = {
        "running": True,
        "matchingProcesses": count,
        "inContainer": any(marker in cgroup for marker in ("docker", "containerd", "libpod")),
        "ageSeconds": int(float(uptime_text.split()[0]) - start_ticks / os.sysconf("SC_CLK_TCK"))
        if uptime_text and start_ticks is not None else None,
        "residentBytes": status.get("VmRSS"),
        "peakResidentBytes": status.get("VmHWM"),
        "threads": status.get("Threads"),
        "openFiles": open_fds,
        "openFilesLimit": _open_files_limit(pid),
        "systemdUnit": unit.group(1) if unit else None,
    }
    return process_info, argv


def _sha256_file(path: str) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def collect_binary(binary: str, gaps: CollectionGaps) -> dict:
    try:
        os.stat(binary)
    except PermissionError:
        gaps.add("roko.binary", "binary not accessible to this user; version still available via RPC")
        return {"present": None, "path": scrub_path(binary)}
    except OSError:
        return {"present": False}
    version = run_command([binary, "--version"], timeout=15)
    if version is None:
        gaps.add("roko.binary.version", "binary --version failed")
    return {"present": True, "path": scrub_path(binary),
            "version": version.strip()[:256] if version else None, "sha256": _sha256_file(binary)}


def detect_deployment(process: dict, service_argv: list[str], binary: dict) -> dict:
    image = parse_key_values(read_text(IMAGE_ENV_FILE)).get("ROKO_IMAGE")
    uses_docker = process.get("inContainer") or any(arg.endswith("docker") for arg in service_argv[:1])
    if uses_docker:
        runtime = "docker"
    elif binary.get("present") or process.get("running"):
        runtime = "native"
    else:
        runtime = "not-detected"
    return {"runtime": runtime, "dockerImageId": image[:80] if image and uses_docker else None}


def node_flags(process_argv: list[str], service_argv: list[str]) -> dict:
    if process_argv:
        return {"source": "running-process", "flags": sanitize_node_arguments(process_argv[1:])}
    if service_argv:
        return {"source": "service-unit", "flags": sanitize_node_arguments(service_argv[1:])}
    return {"source": "not-found", "flags": []}
