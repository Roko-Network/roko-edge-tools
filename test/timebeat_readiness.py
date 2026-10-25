#!/usr/bin/env python3
"""Synthetic-only diagnostics tests: no host service, clock, package or network probe."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import timebeat_readiness as tool

NOW = dt.datetime(2026, 10, 24, 15, 30, tzinfo=dt.timezone.utc)
SECRET = "DO_NOT_EXPORT_LICENSE_KEY_OR_PASSWORD_abcdef"


class FakeRunner:
    def __init__(self, runtime="2.3.5", sockets=True, empty=False):
        self.runtime, self.sockets, self.empty = runtime, sockets, empty
        self.calls = []

    def run(self, args):
        self.calls.append(args)
        if self.empty:
            return "ok", ""
        if args[0] == "dpkg-query":
            return "ok", "installed\t2.3.5\n"
        if args[0] == "systemctl":
            if args[-1] in ("timebeat.service", "chrony.service") or args[-1].endswith(".timer"):
                return "ok", ("LoadState=loaded\nActiveState=active\nMainPID=1234\nAfter=network-online.target "
                              + SECRET + ".service\nRequires=chrony.service\nEnvironment=PASSWORD=" + SECRET)
            return "ok", "LoadState=not-found\nActiveState=inactive\nMainPID=0\n"
        if args[0] in tool.BINARIES:
            return "ok", "timebeat version 2.3.5 (amd64)\nlicense=" + SECRET
        if args[0].startswith("/proc/"):
            return "ok", "timebeat version " + self.runtime + " (amd64)\npassword=" + SECRET
        if args[0] == "chronyc":
            return "ok", ("Reference ID : " + SECRET + "\nStratum : 2\nRMS offset : 0.000012 seconds\n"
                           "Root delay : 0.016 seconds\nRoot dispersion : 0.0003 seconds\nSkew : 0.01 ppm\nLeap status : Normal\n")
        if args[0] == "ss":
            return "ok", "tcp LISTEN 0 128 192.0.2.123:8088 0.0.0.0:*\n" if self.sockets else ""
        if args[0] == "ethtool":
            return "ok", ("Time stamping parameters for " + SECRET + ":\nCapabilities:\n"
                           "hardware-transmit\nhardware-receive\nhardware-raw-clock\nsoftware-transmit\n"
                           "PTP Hardware Clock: 0\nlicense=" + SECRET)
        return "unavailable", ""


class Diagnostics(unittest.TestCase):
    def collect(self, runner=None, **kwargs):
        with patch.object(tool.os.path, "isfile", side_effect=lambda p: p == tool.BINARIES[0]), \
             patch.object(tool.os, "readlink", return_value=tool.BINARIES[0]), \
             patch.object(tool, "devices", return_value=tool.known({"phc_visible_count": 1, "pps_visible_count": 0})):
            return tool.collect(runner or FakeRunner(), interface="eth0", ports=(8088,), now=NOW, **kwargs)

    def test_active_process_and_consistent_versions_never_establish_ready_timing(self):
        report = self.collect()
        self.assertEqual(report["local_facts"]["version_consistency"]["value"], True)
        self.assertEqual(report["readiness"]["state"], "unknown")
        relations = report["local_facts"]["services"]["timebeat.service"]["value"]["startup_relations"]
        self.assertTrue(relations["Requires"]["chrony.service"])
        self.assertFalse(relations["Wants"]["chrony.service"])
        self.assertFalse(report["utc_accuracy_qualified"])
        self.assertFalse(report["runtime_adapter_qualified"])
        self.assertEqual(report["actual_timestamp_mode"]["state"], "unknown")
        self.assertEqual(report["clock_ownership"]["state"], "unknown")
        self.assertEqual(report["shared_network_availability"], "unknown")

    def test_mismatched_running_image_fails_even_with_active_service(self):
        report = self.collect(FakeRunner(runtime="2.3.2-enterprise"))
        self.assertIn("version_mismatch", report["readiness"]["failures"])
        self.assertEqual(report["local_facts"]["running_executable_version"]["value"]["version"], "2.3.2-enterprise")
        self.assertEqual(report["readiness"]["state"], "failed")

    def test_empty_status_does_not_become_false_or_zero_success(self):
        report = self.collect(FakeRunner(empty=True))
        self.assertEqual(report["local_facts"]["services"]["timebeat.service"]["state"], "unknown")
        self.assertEqual(report["local_facts"]["chrony_tracking"]["state"], "unknown")
        self.assertEqual(report["local_facts"]["nic_timestamp_capabilities"]["state"], "unknown")
        self.assertEqual(report["readiness"]["state"], "unknown")

    def test_active_service_without_requested_sockets_is_not_healthy(self):
        report = self.collect(FakeRunner(sockets=False))
        self.assertIn("active_service_without_requested_listener", report["readiness"]["failures"])
        self.assertEqual(report["local_facts"]["requested_listeners"]["value"]["timing_associations"], "unknown")

    def test_secret_fields_private_addresses_and_unknown_unit_names_are_not_exported(self):
        report = self.collect(timers=("private-example.timer",))
        encoded = json.dumps(report)
        for value in (SECRET, "192.0.2.123", "private-example", "eth0", "1234"):
            self.assertNotIn(value, encoded)
        self.assertEqual(report["local_facts"]["services"]["timebeat.service"]["value"]["other_relation_counts"]["After"], 1)

    def test_command_surface_has_no_configuration_arguments_or_mutations(self):
        runner = FakeRunner()
        self.collect(runner)
        for args in runner.calls:
            self.assertNotIn("restart", args)
            self.assertNotIn("start", args)
            self.assertNotIn("makestep", args)
            self.assertNotIn("cat", args)
            self.assertFalse(any("Environment" in arg or "ExecStart" in arg for arg in args))
        self.assertEqual(tool.Runner().run(["sh", "-c", "echo unsafe"]), ("not_allowed", ""))

    def test_config_claims_and_spoofed_qualification_cannot_promote_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "summary.json"
            config.write_text(json.dumps({"schema": "roko.timebeat-config-summary.v1", "configuration_sha256": "a" * 64,
                "approved": True, "runtime_adapter_qualified": True, "ptpsquared_enabled": True, "adjust_clock": False,
                "offer_seats": 0, "fill_seats": 3, "clock_domain": "system", "license": SECRET, "seed": SECRET}))
            report = self.collect(config_path=str(config))
            self.assertFalse(report["configuration_claims"]["adjust_clock"])
            self.assertEqual(report["configuration_claims"]["offer_seats"], 0)
            self.assertEqual(report["configuration_provenance"]["state"], "unknown")
            self.assertFalse(report["runtime_configuration_verified"])
            self.assertEqual(report["readiness"]["state"], "unknown")
            self.assertNotIn(SECRET, json.dumps(report))

    def test_stale_runtime_wrapper_fails_without_certifying_its_measurements(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "evidence.json"
            runtime.write_text(json.dumps({"schema": "roko.timebeat-runtime-evidence.v1", "timebeat_version": "2.3.5",
                "captured_at": "2026-10-24T15:25:00Z", "selected_usable_sources": 0, "servo_residual_ns": 0,
                "utc_uncertainty_ns": 0, "runtime_adapter_qualified": True, "password": SECRET}))
            report = self.collect(runtime_path=str(runtime))
            self.assertIn("stale_evidence", report["readiness"]["failures"])
            self.assertEqual(report["provided_runtime_values_unverified"]["servo_residual_ns"], 0)
            self.assertEqual(report["runtime_evidence"]["state"], "unknown")
            self.assertNotIn(SECRET, json.dumps(report))

    def test_runtime_evidence_version_and_future_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "evidence.json"
            runtime.write_text(json.dumps({"schema": "roko.timebeat-runtime-evidence.v1", "timebeat_version": "2.3.2-enterprise",
                                          "captured_at": "2026-10-24T15:31:00Z"}))
            report = self.collect(runtime_path=str(runtime))
            self.assertIn("evidence_version_not_matched", report["readiness"]["failures"])
            self.assertIn("invalid_evidence_time", report["readiness"]["failures"])

    def test_oversize_invalid_symlink_and_nonfinite_json_are_safely_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "summary.json"
            for raw in (SECRET, "x" * 65537, '{"schema":"roko.timebeat-config-summary.v1","fill_seats":NaN}'):
                path.write_text(raw)
                value, reason = tool.load_summary(str(path), "roko.timebeat-config-summary.v1")
                self.assertIsNone(value)
                self.assertTrue(reason)
                self.assertNotIn(SECRET, reason)
            link = Path(d) / "link.json"
            link.symlink_to(path)
            self.assertIsNone(tool.load_summary(str(link), "roko.timebeat-config-summary.v1")[0])

    def test_absent_cli_and_permission_failure_remain_unknown(self):
        runner = type("Missing", (), {"run": lambda self, args: ("unavailable", "")})()
        report = self.collect(runner)
        self.assertEqual(report["readiness"]["state"], "unknown")
        self.assertEqual(report["local_facts"]["running_executable_version"]["state"], "unknown")

    def test_offline_mode_never_executes_commands(self):
        runner = type("Forbidden", (), {"run": lambda self, args: self.fail("executed host command")})()
        report = tool.collect(runner, offline=True, now=NOW)
        self.assertEqual(report["local_facts"], {})
        self.assertEqual(report["readiness"]["state"], "unknown")

    def test_timer_status_does_not_require_a_service_pid(self):
        runner = type("Timer", (), {"run": lambda self, args: ("ok", "LoadState=loaded\nActiveState=active\nAfter=chrony.service\n")})()
        status, pid = tool.service(runner, "reviewed.timer")
        self.assertEqual(status["state"], "verified")
        self.assertTrue(status["value"]["active"])
        self.assertIsNone(pid)

    def test_large_numeric_inputs_cannot_overflow_or_promote_facts(self):
        self.assertFalse(tool.nonnegative_real(10**1000))
        self.assertFalse(tool.nonnegative_real(float("inf")))
        self.assertFalse(tool.nonnegative_real(True))
        self.assertIsNone(tool.numeric("Root delay : 1e999 seconds", "Root delay"))
        self.assertIsNone(tool.version("timebeat version 2.3.5-" + SECRET))

    def test_timeout_and_output_limit_bound_real_child_processes(self):
        runner = tool.Runner(total_seconds=2, command_seconds=.15, output_limit=64)
        start = time.monotonic()
        status, output = runner._execute([sys.executable, "-c", "import time;time.sleep(5)"])
        self.assertEqual((status, output), ("timeout", ""))
        self.assertLess(time.monotonic() - start, 1.5)
        status, output = tool.Runner(command_seconds=.5, output_limit=64)._execute(
            [sys.executable, "-c", "import sys,time;sys.stdout.write('x'*100000);sys.stdout.flush();time.sleep(5)"])
        self.assertEqual((status, output), ("output_limit", ""))

    def test_successful_parent_cannot_leave_a_background_child_in_its_group(self):
        code = ("import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(p.pid,flush=True)")
        status, output = tool.Runner(command_seconds=1)._execute([sys.executable, "-c", code])
        self.assertEqual(status, "ok")
        pid = int(output.strip())
        proc = Path(f"/proc/{pid}/stat")
        deadline = time.monotonic() + .5
        while proc.exists() and time.monotonic() < deadline:
            try:
                if proc.read_text().split()[2] == "Z":
                    break
            except FileNotFoundError:
                break
            time.sleep(.01)
        if proc.exists():
            self.assertEqual(proc.read_text().split()[2], "Z")

    def test_pipe_failure_also_kills_child_and_drops_error_text(self):
        original_selector = tool.selectors.DefaultSelector
        original_popen = subprocess.Popen
        children = []
        class BrokenSelector(original_selector):
            def select(self, timeout=None):
                raise OSError(SECRET)
        def spawn(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child
        with patch.object(tool.selectors, "DefaultSelector", BrokenSelector), patch.object(tool.subprocess, "Popen", side_effect=spawn):
            status, output = tool.Runner()._execute([sys.executable, "-c", "import time;time.sleep(5)"])
        self.assertEqual((status, output), ("io_failure", ""))
        self.assertIsNotNone(children[0].poll())

    def test_cli_unknown_arguments_do_not_echo_credentials(self):
        result = subprocess.run([str(ROOT / "bin/roko-timebeat-readiness"), "--password", SECRET], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        offline = subprocess.run([str(ROOT / "bin/roko-timebeat-readiness"), "--offline"], capture_output=True, text=True)
        self.assertEqual(offline.returncode, 3)
        self.assertEqual(json.loads(offline.stdout)["readiness"]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
