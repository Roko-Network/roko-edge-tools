"""Bounded local facts and untrusted, sanitized handoff summaries; never a clock controller."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

SCHEMA = "roko.timebeat-readiness.v1"
SERVICES = ("timebeat.service", "chrony.service", "chronyd.service", "ptp4l.service", "phc2sys.service", "systemd-timesyncd.service")
BINARIES = ("/usr/share/timebeat/bin/timebeat", "/usr/bin/timebeat", "/usr/local/bin/timebeat")
PROGRAMS = {"systemctl": ("/usr/bin/systemctl", "/bin/systemctl"),
            "dpkg-query": ("/usr/bin/dpkg-query",), "rpm": ("/usr/bin/rpm",),
            "chronyc": ("/usr/bin/chronyc", "/usr/sbin/chronyc"),
            "ss": ("/usr/bin/ss", "/usr/sbin/ss", "/bin/ss"),
            "ethtool": ("/usr/sbin/ethtool", "/sbin/ethtool", "/usr/bin/ethtool")}
GATES = ("chrony.service", "chronyd.service", "time-sync.target", "network-online.target", "ptp4l.service", "phc2sys.service")


def observation(value=None, state="unknown", reason="not_collected"):
    return {"state": state, "value": value, "reason": reason}


def known(value):
    return observation(value, "verified", "local_observation")


class Runner:
    """No shell, credentials, stderr, unbounded pipe buffering or surviving timeout children."""
    def __init__(self, total_seconds=20, command_seconds=2, output_limit=16384):
        self.deadline = time.monotonic() + total_seconds
        self.command_seconds = command_seconds
        self.output_limit = output_limit

    def run(self, args):
        first = args[0]
        if first in PROGRAMS:
            executable = next((p for p in PROGRAMS[first] if os.access(p, os.X_OK)), None)
        elif first in BINARIES or re.fullmatch(r"/proc/[1-9][0-9]*/exe", first):
            executable = first if os.access(first, os.X_OK) else None
        else:
            return "not_allowed", ""
        if not executable:
            return "unavailable", ""
        return self._execute([executable, *args[1:]])

    def _execute(self, args):
        budget = min(self.command_seconds, self.deadline - time.monotonic())
        if budget <= 0:
            return "budget_exhausted", ""
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"},
                                    start_new_session=True)
        except OSError:
            return "unavailable", ""
        chunks = bytearray()
        end = time.monotonic() + budget
        result = "ok"
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        result = "timeout"
                        break
                    for key, _ in selector.select(min(remaining, .1)):
                        block = os.read(key.fileobj.fileno(), min(4096, self.output_limit + 1 - len(chunks)))
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        chunks.extend(block)
                        if len(chunks) > self.output_limit:
                            result = "output_limit"
                            break
                    if result != "ok":
                        break
            if result == "ok":
                try:
                    proc.wait(timeout=max(.001, end - time.monotonic()))
                except subprocess.TimeoutExpired:
                    result = "timeout"
        except OSError:
            result = "io_failure"
        finally:
            # Includes descendants of an exited parent, I/O errors and interrupts.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=1)
            finally:
                proc.stdout.close()
        if result != "ok":
            return result, ""
        if proc.returncode:
            return "nonzero", ""
        return "ok", chunks.decode("utf-8", errors="replace")


def version(text, package=False):
    token = r"([0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}(?:-enterprise|-[0-9]{1,6}(?:\.[0-9]{1,6})?)?)"
    pattern = r"^" + token + r"$" if package else r"(?im)^timebeat\s+(?:version\s+)?v?" + token + r"(?=\s|$|\()"
    match = re.search(pattern, text.strip())
    return match.group(1) if match else None


def service(runner, unit):
    status, text = runner.run(["systemctl", "show", "--no-pager", "--property=LoadState,ActiveState,MainPID,After,Requires,Wants", "--", unit])
    if status != "ok":
        return observation(reason=status), None
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if fields.get("LoadState") == "not-found":
        return known({"present": False, "active": False}), None
    if fields.get("LoadState") != "loaded" or fields.get("ActiveState") not in ("active", "inactive", "failed", "activating", "deactivating"):
        return observation(reason="invalid_service_status"), None
    pid_text = fields.get("MainPID", "") if not unit.endswith(".timer") else "0"
    if not re.fullmatch(r"[0-9]{1,10}", pid_text):
        return observation(reason="invalid_service_pid"), None
    dependencies = {k: set(fields.get(k, "").split()) for k in ("After", "Requires", "Wants")}
    value = {"present": True, "active": fields["ActiveState"] == "active",
             "startup_relations": {relation: {k: k in units for k in GATES} for relation, units in dependencies.items()},
             "other_relation_counts": {relation: len(units - set(GATES)) for relation, units in dependencies.items()}}
    return known(value), int(pid_text) or None


def numeric(text, label):
    match = re.search(r"(?m)^" + re.escape(label) + r"\s*:\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)(?=\s|$)", text)
    if not match:
        return None
    value = float(match.group(1))
    return value if math.isfinite(value) else None


def chrony(runner):
    status, text = runner.run(["chronyc", "-n", "tracking"])
    if status != "ok":
        return observation(reason=status)
    leap = re.search(r"(?m)^Leap status\s*:\s*(Normal|Insert second|Delete second|Not synchronised)\s*$", text)
    stratum = numeric(text, "Stratum")
    if not leap or stratum is None or not stratum.is_integer() or not 0 <= stratum <= 16:
        return observation(reason="invalid_tracking_status")
    values = {"synchronized_reported": leap.group(1) != "Not synchronised" and 1 <= stratum < 16,
              "stratum": int(stratum), "rms_offset_seconds": numeric(text, "RMS offset"),
              "root_delay_seconds": numeric(text, "Root delay"), "root_dispersion_seconds": numeric(text, "Root dispersion"),
              "skew_ppm": numeric(text, "Skew")}
    # No source names, reference IDs or free-form command lines enter the result.
    return known(values)


def devices(directory="/dev"):
    try:
        names = os.listdir(directory)
        return known({"phc_visible_count": sum(bool(re.fullmatch(r"ptp[0-9]+", n)) for n in names),
                      "pps_visible_count": sum(bool(re.fullmatch(r"pps[0-9]+", n)) for n in names),
                      "scope": "current_device_namespace"})
    except OSError:
        return observation(reason="device_namespace_unavailable")


def timestamps(runner, interface):
    if interface is None:
        return observation(reason="interface_not_selected")
    status, text = runner.run(["ethtool", "-T", interface])
    if status != "ok":
        return observation(reason=status)
    tokens = set(line.strip() for line in text.splitlines())
    modes = {mode: mode in tokens for mode in ("hardware-transmit", "hardware-receive", "hardware-raw-clock", "software-transmit", "software-receive", "software-system-clock")}
    phc = re.search(r"(?m)^PTP Hardware Clock:\s*(-?[0-9]+)\s*$", text)
    if not phc or not any(modes.values()):
        return observation(reason="invalid_timestamp_capabilities")
    return known({"capabilities": modes, "phc_index_reported": int(phc.group(1)) if int(phc.group(1)) >= 0 else None,
                  "actual_timestamp_mode": "unknown", "actual_clock_domain": "unknown"})


def listeners(runner, ports):
    if not ports:
        return observation(reason="no_approved_ports_selected")
    status, text = runner.run(["ss", "-H", "-lntu"])
    if status != "ok":
        return observation(reason=status)
    counts = {str(p): 0 for p in ports}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 5:
            return observation(reason="invalid_socket_status")
        match = re.search(r":([0-9]+)$", fields[4])
        if match and match.group(1) in counts:
            counts[match.group(1)] += 1
    return known({"requested_port_listener_counts": counts, "process_ownership": "unknown",
                  "timing_associations": "unknown"})


def load_summary(path, expected_schema):
    if path is None:
        return None, "not_provided"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return None, "invalid_summary_file"
            raw = stream.read(65537)
        if len(raw) > 65536:
            return None, "summary_size_limit"
        data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(data, dict) or data.get("schema") != expected_schema:
            return None, "invalid_summary_schema"
        return data, None
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None, "invalid_summary_file"


def stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z", value):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_fields(data, specification):
    result = {}
    for key, validate in specification.items():
        value = data.get(key)
        result[key] = value if validate(value) else None
    return result


def boolean(value):
    return type(value) is bool


def unsigned(value):
    return type(value) is int and 0 <= value <= 0xffffffff


def nonnegative_real(value):
    if type(value) is int:
        return 0 <= value <= 2**53 - 1
    return type(value) is float and math.isfinite(value) and 0 <= value <= 2**53 - 1


def enum(*values):
    return lambda value: type(value) is str and value in values


def summarize_inputs(config_path, runtime_path, now, actual_version):
    config, config_error = load_summary(config_path, "roko.timebeat-config-summary.v1")
    runtime, runtime_error = load_summary(runtime_path, "roko.timebeat-runtime-evidence.v1")
    config_claims = {}
    provenance = observation(reason=config_error or "operator_summary_not_bound_to_running_process")
    if config is not None:
        digest = config.get("configuration_sha256")
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            provenance["value"] = {"configuration_sha256": digest}
        config_claims = safe_fields(config, {
            "ptpsquared_enabled": boolean, "adjust_clock": boolean, "domain": lambda v: unsigned(v) and v <= 255,
            "offer_seats": unsigned, "fill_seats": unsigned, "concurrent_sources": unsigned,
            "clock_domain": enum("system", "phc", "unknown"), "adjustment_owner": enum("chrony", "timebeat", "ptp4l", "phc2sys", "other", "unknown"),
            "interface_supplied": boolean, "source_kind": enum("vendor_mesh", "managed_feed", "operator_mesh", "unknown"),
            "bootstrap_count": unsigned, "ptp_log_sync_interval": lambda v: type(v) is int and -128 <= v <= 127,
            "report_interval_seconds": unsigned})
    evidence = observation(reason=runtime_error or "runtime_adapter_not_qualified")
    freshness = observation(reason="runtime_evidence_unavailable")
    values = {}
    if runtime is not None:
        captured = stamp(runtime.get("captured_at"))
        age = (now - captured).total_seconds() if captured else None
        if age is None or age < -5:
            freshness = observation(state="failed", reason="invalid_evidence_time")
        elif age > 150:
            freshness = observation(round(age, 3), "failed", "stale_evidence")
        else:
            freshness = known(max(age, 0))
        evidence_version = version(runtime.get("timebeat_version", ""), package=True) if isinstance(runtime.get("timebeat_version"), str) else None
        if not evidence_version or not actual_version or evidence_version != actual_version:
            evidence = observation(state="failed" if actual_version and evidence_version else "unknown", reason="evidence_version_not_matched")
        values = safe_fields(runtime, {"discovered_peers": unsigned, "connected_peers": unsigned, "occupied_seats": unsigned,
            "selected_usable_sources": unsigned, "utc_sample_age_seconds": nonnegative_real,
            "utc_uncertainty_ns": unsigned, "servo_residual_ns": lambda v: type(v) is int and -(2**63) <= v <= 2**63 - 1,
            "clock_domain": enum("system", "phc", "unknown"), "timestamp_mode": enum("hardware", "software", "unknown"),
            "adjustment_observed": boolean, "protocol_exchange_hz": lambda v: nonnegative_real(v) and v <= 1000000})
    return {"configuration_provenance": provenance, "configuration_claims": config_claims,
            "runtime_evidence": evidence, "runtime_evidence_age_seconds": freshness,
            "provided_runtime_values_unverified": values,
            "runtime_configuration_verified": False, "runtime_adapter_qualified": False}


def collect(runner, config_path=None, runtime_path=None, interface=None, ports=(), timers=(), offline=False, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    facts = {}
    package_version = disk_version = running_version = None
    failures = []
    if not offline:
        status, text = runner.run(["dpkg-query", "-W", "-f=${db:Status-Status}\t${Version}\n", "timebeat"])
        if status == "ok" and text.startswith("installed\t"):
            package_version = version(text.split("\t", 1)[1].strip(), package=True)
        elif status == "unavailable":
            status, text = runner.run(["rpm", "-q", "--qf", "%{VERSION}\n", "timebeat"])
            if status == "ok":
                package_version = version(text, package=True)
        facts["package_version"] = known(package_version) if package_version else observation(reason="package_version_unavailable")
        units = {}
        main_pid = None
        for unit in SERVICES:
            units[unit], pid = service(runner, unit)
            if unit == "timebeat.service":
                main_pid = pid
        facts["services"] = units
        timebeat = units["timebeat.service"]
        if timebeat["state"] == "verified" and not timebeat["value"]["active"]:
            failures.append("timebeat_not_active")
        disk = next((path for path in BINARIES if os.path.isfile(path)), None)
        if disk:
            status, text = runner.run([disk, "version"])
            disk_version = version(text) if status == "ok" else None
        facts["disk_binary_version"] = known(disk_version) if disk_version else observation(reason="disk_version_unavailable")
        facts["running_executable_version"] = observation(reason="running_executable_unavailable")
        if main_pid:
            try:
                target = os.readlink(f"/proc/{main_pid}/exe")
                deleted = target.endswith(" (deleted)")
                if target.removesuffix(" (deleted)") in BINARIES:
                    status, text = runner.run([f"/proc/{main_pid}/exe", "version"])
                    running_version = version(text) if status == "ok" else None
                    facts["running_executable_version"] = known({"version": running_version, "deleted": deleted}) if running_version else observation(reason="running_version_unavailable")
            except OSError:
                pass
        versions = [v for v in (package_version, disk_version, running_version) if v]
        if len({v.split("-")[0] for v in versions}) > 1:
            failures.append("version_mismatch")
        facts["version_consistency"] = observation(state="failed", reason="version_mismatch") if "version_mismatch" in failures else (
            known(True) if len(versions) == 3 and len(set(versions)) == 1 else observation(reason="incomplete_or_unmatched_version_evidence"))
        facts["chrony_tracking"] = chrony(runner)
        facts["devices"] = devices()
        facts["nic_timestamp_capabilities"] = timestamps(runner, interface)
        facts["requested_listeners"] = listeners(runner, ports)
        sockets = facts["requested_listeners"]
        if timebeat["state"] == "verified" and timebeat["value"]["active"] and sockets["state"] == "verified" and not any(sockets["value"]["requested_port_listener_counts"].values()):
            failures.append("active_service_without_requested_listener")
        facts["recovery_timers"] = {f"timer_{i+1}": service(runner, timer)[0] for i, timer in enumerate(timers)}
    inputs = summarize_inputs(config_path, runtime_path, now, running_version)
    for field in ("runtime_evidence", "runtime_evidence_age_seconds"):
        if inputs[field]["state"] == "failed":
            failures.append(inputs[field]["reason"])
    return {"schema": SCHEMA, "captured_at": now.isoformat().replace("+00:00", "Z"),
            "collection_scope": "local_os_namespace", "timebase": "local_system_clock_not_independently_qualified", "local_facts": facts,
            **inputs, "clock_ownership": observation(reason="service_activity_is_not_adjustment_ownership"),
            "actual_timestamp_mode": observation(reason="capability_is_not_runtime_selection"),
            "utc_source_freshness": observation(reason="runtime_source_semantics_not_qualified"),
            "reporting_cadence": observation(reason="one_shot_tool_does_not_attest_external_schedule"),
            "protocol_rate_qualification": observation(reason="provider_version_rate_contract_unavailable"),
            "startup_gate_qualification": observation(reason="unit_relations_do_not_verify_gate_logic"),
            "recovery_automation_inventory": observation(reason="operator_selected_timers_only"),
            "license_validity": observation(reason="license_not_inspected"),
            "utc_accuracy_qualified": False, "shared_network_availability": "unknown", "trial_24h_status": "not_assessed",
            "readiness": {"state": "failed" if failures else "unknown", "failures": sorted(set(failures)),
                          "remaining_gates": ["runtime_cli_adapter_qualification", "approved_clock_domain_map", "recovery_and_startup_policy_review",
                                              "provider_connection_contract", "isolated_24h_trial"]}}
