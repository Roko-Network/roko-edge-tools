"""Collect OS, platform, CPU and memory facts from /proc, /sys and lscpu without root."""

from __future__ import annotations

import json
import os
import platform

from node_snapshot.probe_io import CollectionGaps, parse_key_values, read_int, read_text, run_command

DMI_FIELDS = {
    "systemVendor": "sys_vendor", "productName": "product_name",
    "boardVendor": "board_vendor", "boardName": "board_name", "chassisType": "chassis_type",
}
CPU_FEATURES_OF_INTEREST = (
    "aes", "avx", "avx2", "avx512f", "sha_ni", "sse4_2", "bmi2", "adx",
    "sha1", "sha2", "pmull", "asimd", "atomics", "crc32",
)


def collect_os(gaps: CollectionGaps) -> dict:
    release = parse_key_values(read_text("/etc/os-release", gaps, "os.release"))
    virt = run_command(["systemd-detect-virt"], ok_codes=(0, 1))
    uptime = read_text("/proc/uptime")
    return {
        "id": release.get("ID"),
        "idLike": release.get("ID_LIKE"),
        "versionId": release.get("VERSION_ID"),
        "prettyName": release.get("PRETTY_NAME"),
        "kernelRelease": platform.release(),
        "architecture": platform.machine(),
        "virtualization": virt.strip() if virt else None,
        "inContainer": os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"),
        "uptimeSeconds": int(float(uptime.split()[0])) if uptime else None,
        "pythonVersion": platform.python_version(),
    }


def collect_platform(gaps: CollectionGaps) -> dict:
    facts = {name: read_text(f"/sys/class/dmi/id/{leaf}") for name, leaf in DMI_FIELDS.items()}
    facts["deviceTreeModel"] = read_text("/proc/device-tree/model")
    if not any(facts.values()):
        gaps.add("platform.model", "no DMI or device-tree model readable")
    return facts


def _flatten_lscpu(entries: list, out: dict) -> None:
    for entry in entries:
        out[str(entry.get("field", "")).rstrip(":")] = entry.get("data")
        _flatten_lscpu(entry.get("children") or [], out)


def _lscpu_fields() -> dict:
    raw = run_command(["lscpu", "-J"])
    fields: dict = {}
    if raw:
        try:
            _flatten_lscpu(json.loads(raw).get("lscpu", []), fields)
        except (ValueError, AttributeError):
            return {}
    return fields


def _cpuinfo_summary() -> dict:
    model, features = None, set()
    for line in (read_text("/proc/cpuinfo") or "").splitlines():
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if key in ("model name", "hardware", "cpu model") and not model:
            model = value.strip()
        elif key in ("flags", "features") and not features:
            features = set(value.split())
    return {"model": model, "features": features}


def _cgroup_cpu_limit() -> float | None:
    quota = read_text("/sys/fs/cgroup/cpu.max")
    if not quota or quota.startswith("max"):
        return None
    limit, period = quota.split()[:2]
    return round(int(limit) / int(period), 2)


def collect_cpu(gaps: CollectionGaps) -> dict:
    fields, info = _lscpu_fields(), _cpuinfo_summary()
    if not fields:
        gaps.add("cpu.topology", "lscpu unavailable; topology from /proc only")
    features = info["features"] or set((fields.get("Flags") or "").split())
    try:
        usable = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        usable = None
    return {
        "model": fields.get("Model name") or info["model"],
        "vendor": fields.get("Vendor ID"),
        "logicalCpus": os.cpu_count(),
        "usableCpus": usable,
        "sockets": _int_or_none(fields.get("Socket(s)")),
        "coresPerSocket": _int_or_none(fields.get("Core(s) per socket") or fields.get("Core(s) per cluster")),
        "threadsPerCore": _int_or_none(fields.get("Thread(s) per core")),
        "numaNodes": _int_or_none(fields.get("NUMA node(s)")),
        "maxMhz": _float_or_none(fields.get("CPU max MHz")),
        "scalingGovernor": read_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "cgroupCpuLimit": _cgroup_cpu_limit(),
        "featuresOfInterest": sorted(f for f in CPU_FEATURES_OF_INTEREST if f in features),
    }


def collect_memory(gaps: CollectionGaps) -> dict:
    meminfo = {}
    for line in (read_text("/proc/meminfo", gaps, "memory.meminfo") or "").splitlines():
        key, _, value = line.partition(":")
        parts = value.split()
        if parts and parts[0].isdigit():
            meminfo[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    total, available = meminfo.get("MemTotal"), meminfo.get("MemAvailable")
    thp = read_text("/sys/kernel/mm/transparent_hugepage/enabled") or ""
    cgroup_max = read_text("/sys/fs/cgroup/memory.max")
    return {
        "totalBytes": total,
        "availableBytes": available,
        "usedPercent": round(100 * (total - available) / total, 1) if total and available is not None else None,
        "swapTotalBytes": meminfo.get("SwapTotal"),
        "swapUsedBytes": (meminfo["SwapTotal"] - meminfo["SwapFree"]) if "SwapFree" in meminfo else None,
        "hugePagesTotal": meminfo.get("HugePages_Total"),
        "transparentHugePages": thp[thp.find("[") + 1:thp.find("]")] if "[" in thp else None,
        "swappiness": read_int("/proc/sys/vm/swappiness"),
        "cgroupMemoryLimitBytes": _int_or_none(cgroup_max),
    }


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None
