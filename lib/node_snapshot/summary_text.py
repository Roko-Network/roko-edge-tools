"""Render a short human-readable summary of a node system snapshot."""

from __future__ import annotations

GIB = 1024 ** 3


def _gib(value) -> str:
    return f"{value / GIB:.1f} GiB" if isinstance(value, (int, float)) else "n/a"


def _hardware_lines(snap: dict) -> list[str]:
    host, cpu, mem = snap["host"], snap["host"]["cpu"], snap["host"]["memory"]
    model = host["platform"].get("productName") or host["platform"].get("deviceTreeModel") or "n/a"
    return [
        f"os:        {host['os'].get('prettyName')} ({host['os'].get('architecture')}, kernel {host['os'].get('kernelRelease')})",
        f"platform:  {model}; virtualization={host['os'].get('virtualization')}",
        f"cpu:       {cpu.get('model')} | {cpu.get('logicalCpus')} logical, usable {cpu.get('usableCpus')}",
        f"memory:    {_gib(mem.get('totalBytes'))} total, {mem.get('usedPercent')}% used, swap {_gib(mem.get('swapTotalBytes'))}",
    ]


def _storage_lines(snap: dict) -> list[str]:
    fs, chain = snap["storage"]["dataFilesystem"], snap["storage"]["chainData"]
    rotational = fs.get("backingDiskRotational")
    media = "unknown" if rotational is None else ("HDD" if rotational else "SSD/NVMe")
    return [
        f"data fs:   {fs.get('basePath')} on {fs.get('fsType')} ({fs.get('backingDisk')}, {media}); "
        f"{_gib(fs.get('availableBytes'))} free of {_gib(fs.get('totalBytes'))}",
        f"chain db:  {_gib(chain.get('totalBytes'))} across {len(chain.get('chains', []))} chain dir(s)",
    ]


def _roko_lines(snap: dict) -> list[str]:
    roko, node = snap["roko"], snap["node"]
    service, process = roko["service"], roko["process"]
    lines = [
        f"runtime:   {roko['deployment']['runtime']}; binary {roko['binary'].get('version') or node.get('version') or 'n/a'}",
        f"service:   {service.get('name')} {service.get('activeState')} restarts={service.get('restartCount')}",
        f"process:   running={process.get('running')} rss={_gib(process.get('residentBytes'))}",
    ]
    if node.get("reachable"):
        lines.append(f"node:      {node.get('chain')} spec {node.get('specVersion')} peers={node.get('peers')} "
                     f"syncing={node.get('isSyncing')} finalized={node.get('finalizedBlock')}")
    return lines


def _utilization_lines(snap: dict) -> list[str]:
    util = snap["utilization"]
    cpu = util.get("cpuPercent") or {}
    lines = [f"load:      {util.get('loadAverage')} cpu busy={cpu.get('busy')}% iowait={cpu.get('iowait')}% "
             f"steal={cpu.get('steal')}% over {util.get('sampleSeconds')}s"]
    for disk in util.get("disks", [])[:4]:
        lines.append(f"disk {disk['device']}: r={disk['readIops']}/s w={disk['writeIops']}/s busy={disk['busyPercent']}%")
    return lines


def render_summary(snap: dict, output_path: str | None) -> str:
    lines = ["ROKO node system snapshot", f"generated: {snap['generatedAt']}  id: {snap['snapshotId']}"]
    for title, section in (("hardware", _hardware_lines), ("storage", _storage_lines),
                           ("roko", _roko_lines), ("utilization", _utilization_lines)):
        lines.append(f"\n== {title} ==")
        lines.extend(section(snap))
    lines.append("\n== documented checks ==")
    for check in snap["checks"]:
        lines.append(f"{check['status']:>7}  {check['id']}: {check['observed']} (expected {check['expected']})")
    if snap["collectionGaps"]:
        lines.append(f"\n{len(snap['collectionGaps'])} item(s) not collected; see collectionGaps in the JSON.")
    if output_path:
        lines.append(f"\nwrote {output_path} (mode 0600). Review it before sharing.")
    return "\n".join(lines)
