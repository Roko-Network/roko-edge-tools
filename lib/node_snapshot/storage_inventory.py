"""Collect block devices, the node data filesystem and chain database sizes without root."""

from __future__ import annotations

import json
import os

from node_snapshot.privacy_filter import filter_mount_options, scrub_path
from node_snapshot.probe_io import CollectionGaps, read_int, read_text, run_command, to_int

SKIPPED_DEVICE_PREFIXES = ("loop", "ram", "sr", "fd")
MAX_DEVICES = 64


def _flatten_lsblk(devices: list, parent: str | None, out: list) -> None:
    for device in devices:
        name = str(device.get("name", ""))
        if not name.startswith(SKIPPED_DEVICE_PREFIXES) and len(out) < MAX_DEVICES:
            rota = device.get("rota")
            out.append({
                "name": name,
                "parent": parent,
                "type": device.get("type"),
                "sizeBytes": to_int(device.get("size")),
                "rotational": rota in (True, "1", 1),
                "transport": device.get("tran"),
                "model": (device.get("model") or "").strip() or None,
                "fsType": device.get("fstype"),
                "mountpoint": scrub_path(device.get("mountpoint")),
            })
        _flatten_lsblk(device.get("children") or [], name, out)


def collect_block_devices(gaps: CollectionGaps) -> list[dict]:
    raw = run_command(["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,ROTA,TRAN,MODEL,FSTYPE,MOUNTPOINT"])
    devices: list[dict] = []
    if raw:
        try:
            _flatten_lsblk(json.loads(raw).get("blockdevices", []), None, devices)
            return devices
        except (ValueError, AttributeError):
            pass
    gaps.add("storage.blockDevices", "lsblk unavailable; using /sys/block")
    for name in sorted(os.listdir("/sys/block")) if os.path.isdir("/sys/block") else []:
        if name.startswith(SKIPPED_DEVICE_PREFIXES):
            continue
        sectors = read_int(f"/sys/block/{name}/size")
        devices.append({
            "name": name, "parent": None, "type": "disk",
            "sizeBytes": sectors * 512 if sectors is not None else None,
            "rotational": read_text(f"/sys/block/{name}/queue/rotational") == "1",
            "transport": None, "model": read_text(f"/sys/block/{name}/device/model"),
            "fsType": None, "mountpoint": None,
        })
    return devices[:MAX_DEVICES]


def _existing_ancestor(path: str) -> str:
    while path and not os.path.exists(path):
        path = os.path.dirname(path.rstrip("/")) or "/"
    return path or "/"


def _mount_for(path: str) -> dict:
    best: dict = {}
    for line in (read_text("/proc/self/mounts") or "").splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        mountpoint = fields[1].replace("\\040", " ")
        inside = path == mountpoint or path.startswith(mountpoint.rstrip("/") + "/")
        if inside and len(mountpoint) >= len(best.get("mountpoint", "")):
            best = {"mountpoint": mountpoint, "device": fields[0], "fsType": fields[2],
                    "options": filter_mount_options(fields[3])}
    return best


def block_device_for_path(path: str) -> str | None:
    """Return the whole-disk kernel name backing a path (e.g. nvme0n1), if resolvable."""
    try:
        device = os.stat(_existing_ancestor(path)).st_dev
        sys_dir = os.path.realpath(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}")
    except OSError:
        return None
    if os.path.exists(os.path.join(sys_dir, "partition")):
        sys_dir = os.path.dirname(sys_dir)
    name = os.path.basename(sys_dir)
    return name if os.path.isdir(f"/sys/block/{name}") else None


def collect_data_filesystem(base_path: str, gaps: CollectionGaps) -> dict:
    probe = _existing_ancestor(base_path)
    try:
        stat = os.statvfs(probe)
    except OSError:
        gaps.add("storage.dataFilesystem", "statvfs failed")
        return {"basePath": scrub_path(base_path), "basePathExists": os.path.exists(base_path)}
    mount = _mount_for(os.path.realpath(probe))
    disk = block_device_for_path(base_path)
    return {
        "basePath": scrub_path(base_path),
        "basePathExists": os.path.exists(base_path),
        "mountpoint": scrub_path(mount.get("mountpoint")),
        "fsType": mount.get("fsType"),
        "mountOptions": mount.get("options", []),
        "backingDisk": disk,
        "backingDiskRotational": read_text(f"/sys/block/{disk}/queue/rotational") == "1" if disk else None,
        "ioScheduler": _active_scheduler(disk),
        "totalBytes": stat.f_blocks * stat.f_frsize,
        "availableBytes": stat.f_bavail * stat.f_frsize,
        "usedPercent": round(100 * (1 - stat.f_bavail / stat.f_blocks), 1) if stat.f_blocks else None,
        "inodesUsedPercent": round(100 * (1 - stat.f_favail / stat.f_files), 1) if stat.f_files else None,
    }


def _active_scheduler(disk: str | None) -> str | None:
    text = read_text(f"/sys/block/{disk}/queue/scheduler") if disk else None
    if text and "[" in text:
        return text[text.find("[") + 1:text.find("]")]
    return text


def _disk_usage_bytes(path: str, timeout: float) -> int | None:
    out = run_command(["du", "-s", "-B1", "-x", path], timeout=timeout)
    return to_int(out.split()[0]) if out and out.split() else None


def collect_chain_data(base_path: str, measure: bool, gaps: CollectionGaps) -> dict:
    chains_dir = os.path.join(base_path, "chains")
    try:
        names = sorted(os.listdir(chains_dir))[:16]
    except OSError as error:
        gaps.add("storage.chainData", f"chains directory not listable ({type(error).__name__})")
        return {"chains": [], "totalBytes": None}
    chains = []
    for name in names:
        db_dir = os.path.join(chains_dir, name, "db")
        try:
            backends = sorted(os.listdir(db_dir))[:8]
        except OSError:
            backends = []
        size = _disk_usage_bytes(os.path.join(chains_dir, name), 120) if measure else None
        if measure and size is None:
            gaps.add("storage.chainData", "du failed or timed out (permissions or size)")
        chains.append({"chain": name[:64], "databaseDirs": backends, "sizeBytes": size})
    sizes = [c["sizeBytes"] for c in chains if c["sizeBytes"] is not None]
    return {"chains": chains, "totalBytes": sum(sizes) if sizes and len(sizes) == len(chains) else None}
