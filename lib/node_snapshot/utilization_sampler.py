"""Measure CPU, disk, network, pressure and node-process utilization over a short window."""

from __future__ import annotations

import os
import time

from node_snapshot.probe_io import read_text

CPU_FIELDS = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
SECTOR_BYTES = 512
CLOCK_TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _cpu_counters() -> list[int]:
    line = (read_text("/proc/stat") or "").splitlines()[0:1]
    if not line or not line[0].startswith("cpu "):
        return []
    return [int(value) for value in line[0].split()[1:9]]


def _disk_counters(disks: list[str]) -> dict:
    counters = {}
    for line in (read_text("/proc/diskstats") or "").splitlines():
        fields = line.split()
        if len(fields) >= 14 and fields[2] in disks:
            counters[fields[2]] = [int(fields[i]) for i in (3, 5, 7, 9, 12)]
    return counters


def _net_counters(interfaces: list[str]) -> dict:
    counters = {}
    for name in interfaces:
        rx = read_text(f"/sys/class/net/{name}/statistics/rx_bytes")
        tx = read_text(f"/sys/class/net/{name}/statistics/tx_bytes")
        if rx and tx and rx.isdigit() and tx.isdigit():
            counters[name] = (int(rx), int(tx))
    return counters


def _process_ticks(pid: int | None) -> int | None:
    stat = read_text(f"/proc/{pid}/stat") if pid else None
    if not stat or ")" not in stat:
        return None
    fields = stat.rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def _snapshot(disks: list[str], interfaces: list[str], pid: int | None) -> dict:
    return {"time": time.monotonic(), "cpu": _cpu_counters(), "disk": _disk_counters(disks),
            "net": _net_counters(interfaces), "proc": _process_ticks(pid)}


def _cpu_percentages(before: list[int], after: list[int]) -> dict:
    if not before or not after:
        return {}
    deltas = [b - a for a, b in zip(before, after)]
    total = sum(deltas) or 1
    shares = {name: round(100 * delta / total, 1) for name, delta in zip(CPU_FIELDS, deltas)}
    shares["busy"] = round(100 - shares["idle"] - shares["iowait"], 1)
    return shares


def _disk_rates(before: dict, after: dict, seconds: float) -> list[dict]:
    rates = []
    for name, end in sorted(after.items()):
        start = before.get(name)
        if not start:
            continue
        reads, read_sectors, writes, write_sectors, busy_ms = (e - s for s, e in zip(start, end))
        rates.append({
            "device": name,
            "readIops": round(reads / seconds, 1),
            "writeIops": round(writes / seconds, 1),
            "readBytesPerSec": int(read_sectors * SECTOR_BYTES / seconds),
            "writeBytesPerSec": int(write_sectors * SECTOR_BYTES / seconds),
            "busyPercent": round(min(100.0, busy_ms / (seconds * 10)), 1),
        })
    return rates


def _net_rates(before: dict, after: dict, seconds: float) -> list[dict]:
    return [{"interface": name, "rxBytesPerSec": int((rx - before[name][0]) / seconds),
             "txBytesPerSec": int((tx - before[name][1]) / seconds)}
            for name, (rx, tx) in sorted(after.items()) if name in before]


def read_pressure() -> dict:
    """Linux PSI averages (percent of time stalled) for cpu, memory and io."""
    pressure = {}
    for resource in ("cpu", "memory", "io"):
        for line in (read_text(f"/proc/pressure/{resource}") or "").splitlines():
            kind, *pairs = line.split()
            values = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
            pressure[f"{resource}{kind.capitalize()}Avg60"] = float(values.get("avg60", 0))
    return pressure


def sample_utilization(seconds: float, disks: list[str], interfaces: list[str], pid: int | None) -> dict:
    load = (read_text("/proc/loadavg") or "").split()
    result = {
        "sampleSeconds": seconds,
        "loadAverage": [float(value) for value in load[:3]] if len(load) >= 3 else None,
        "pressure": read_pressure(),
    }
    if seconds <= 0:
        return result
    before = _snapshot(disks, interfaces, pid)
    time.sleep(seconds)
    after = _snapshot(disks, interfaces, pid)
    elapsed = max(after["time"] - before["time"], 0.001)
    result.update({
        "sampleSeconds": round(elapsed, 2),
        "cpuPercent": _cpu_percentages(before["cpu"], after["cpu"]),
        "disks": _disk_rates(before["disk"], after["disk"], elapsed),
        "network": _net_rates(before["net"], after["net"], elapsed),
    })
    if before["proc"] is not None and after["proc"] is not None:
        result["nodeProcessCpuPercentOfOneCore"] = round(
            100 * (after["proc"] - before["proc"]) / CLOCK_TICKS / elapsed, 1)
    return result
