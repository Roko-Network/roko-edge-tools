"""Sample candidate servers politely and rank eligible stratum-1 servers by round-trip delay."""

from __future__ import annotations

import socket
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from stratum1_select.ntp_probe import LEAP_ALARM, NTP_PORT, ProbeRejected, query_once, resolve

MIN_GOOD_SAMPLES = 2


def _split_host_port(target: str) -> tuple[str, int]:
    host, sep, port = target.rpartition(":")
    if sep and port.isdigit() and "]" not in port and host.count(":") == 0:
        return host, int(port)
    return target, NTP_PORT


def measure_candidate(candidate: dict, samples: int, spacing: float, timeout: float) -> dict:
    """Query one server `samples` times, at least `spacing` seconds apart."""
    host, port = _split_host_port(candidate["host"])
    result = {**candidate, "samples": [], "errors": []}
    try:
        family, address = resolve(host, port)
    except (socket.gaierror, UnicodeError):
        result["errors"].append("name does not resolve")
        return result
    for index in range(samples):
        if index:
            time.sleep(spacing)
        try:
            result["samples"].append(query_once(family, address, timeout))
        except ProbeRejected as rejected:
            result["errors"].append(rejected.reason)
            if rejected.stop:
                break
        except OSError:
            result["errors"].append("no reply")
    return result


def summarize(measured: dict) -> dict:
    good = [s for s in measured["samples"] if s["leap"] != LEAP_ALARM]
    strata = {s["stratum"] for s in good}
    summary = {key: measured.get(key) for key in ("host", "operator", "region")}
    summary.update({"replies": len(measured["samples"]), "errors": sorted(set(measured["errors"]))})
    if len(good) < MIN_GOOD_SAMPLES:
        return {**summary, "eligible": False, "reason": "too few usable replies"}
    best = min(good, key=lambda s: s["delay"])
    summary.update({
        "stratum": strata.pop() if len(strata) == 1 else sorted(strata),
        "minDelayMs": round(best["delay"] * 1000, 2),
        "offsetMs": round(statistics.median(s["offset"] for s in good) * 1000, 3),
        "offsetSpreadMs": round((max(s["offset"] for s in good) - min(s["offset"] for s in good)) * 1000, 3),
    })
    if summary["stratum"] != 1:
        return {**summary, "eligible": False, "reason": "not stratum 1"}
    if any(e.startswith("kiss-o'-death") for e in summary["errors"]):
        return {**summary, "eligible": False, "reason": "server asked clients to back off"}
    return {**summary, "eligible": True, "reason": None}


def measure_all(candidates: list[dict], samples: int, spacing: float, timeout: float) -> list[dict]:
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(candidates)))) as pool:
        measured = list(pool.map(lambda c: measure_candidate(c, samples, spacing, timeout), candidates))
    ranked = [summarize(m) for m in measured]
    return sorted(ranked, key=lambda r: (not r["eligible"], r.get("minDelayMs") or float("inf")))


def choose_sources(ranked: list[dict], count: int) -> list[dict]:
    """Pick the nearest eligible servers, preferring different operators for failure diversity."""
    eligible = [r for r in ranked if r["eligible"]]
    chosen: list[dict] = []
    for server in eligible:
        if len(chosen) >= count:
            break
        if server.get("operator") not in {c.get("operator") for c in chosen}:
            chosen.append(server)
    for server in eligible:
        if len(chosen) >= count:
            break
        if server not in chosen:
            chosen.append(server)
    return chosen
