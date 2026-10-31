"""Collect clock discipline state (Chrony, timedatectl, Timebeat, PTP clocks) without source identities."""

from __future__ import annotations

import os
import re

from node_snapshot.probe_io import CollectionGaps, parse_key_values, read_text, run_command

TRACKING_FIELDS = {"Stratum": "stratum", "System time": "systemTimeOffsetSeconds",
                   "Last offset": "lastOffsetSeconds", "RMS offset": "rmsOffsetSeconds",
                   "Frequency": "frequencyPpm", "Skew": "skewPpm", "Root delay": "rootDelaySeconds",
                   "Root dispersion": "rootDispersionSeconds", "Leap status": "leapStatus"}
TIME_SERVICES = ("chrony", "chronyd", "systemd-timesyncd", "ntp", "ntpd", "timebeat")
CHRONY_SOCKET = "/run/chrony/chronyd.sock"


def _signed_number(text: str) -> float | None:
    match = re.search(r"[-+]?\d+(\.\d+)?", text)
    if not match:
        return None
    value = float(match.group(0))
    return -value if (" slow" in text or text.strip().startswith("-")) and value > 0 else value


def collect_chrony(gaps: CollectionGaps) -> dict | None:
    tracking = run_command(["chronyc", "-n", "tracking"], timeout=5)
    if tracking is None:
        gaps.add("time.chrony", "chronyc unavailable or chronyd not running")
        return None
    result: dict = {}
    for key, value in parse_key_values(tracking, ":").items():
        if key in TRACKING_FIELDS:
            field = TRACKING_FIELDS[key]
            result[field] = value if field == "leapStatus" else _signed_number(value)
    sources = run_command(["chronyc", "-n", "sources"], timeout=5) or ""
    states = [line[1] for line in sources.splitlines() if len(line) > 1 and line[0] in "^=#" and line[1] in "*+-?x~"]
    result.update({
        "sourcesTotal": len(states),
        "sourcesSelected": states.count("*"),
        "sourcesCombined": states.count("+"),
        "sourcesUnreachable": states.count("?") + states.count("x"),
    })
    return result


def _service_states() -> dict:
    states = {}
    for service in TIME_SERVICES:
        state = run_command(["systemctl", "is-active", f"{service}.service"], ok_codes=(0, 3, 4))
        if state and state.strip() not in ("inactive", "unknown"):
            states[service] = state.strip()
    return states


def _ptp_clocks() -> list[str]:
    root = "/sys/class/ptp"
    names = sorted(os.listdir(root)) if os.path.isdir(root) else []
    return [read_text(f"{root}/{name}/clock_name") or name for name in names][:16]


def collect_time(gaps: CollectionGaps) -> dict:
    timedate = parse_key_values(run_command(["timedatectl", "show"], timeout=5))
    return {
        "ntpSynchronized": timedate.get("NTPSynchronized") == "yes" if timedate else None,
        "rtcInLocalTime": timedate.get("LocalRTC") == "yes" if timedate else None,
        "activeTimeServices": _service_states(),
        "chronySocketPresent": os.path.exists(CHRONY_SOCKET),
        "chrony": collect_chrony(gaps),
        "ptpHardwareClocks": _ptp_clocks(),
    }
