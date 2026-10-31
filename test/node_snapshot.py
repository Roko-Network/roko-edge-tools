#!/usr/bin/env python3
"""Tests for roko-node-snapshot: privacy filtering, parsers, checks and the v1 contract."""

import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from node_snapshot import documented_checks, network_inventory, privacy_filter, roko_rpc, snapshot_cli, time_sync  # noqa: E402

SCHEMA = json.loads((ROOT / "contracts" / "node-system-snapshot-v1.schema.json").read_text())
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
         "integer": int, "number": (int, float)}


def schema_errors(value, schema, path="$"):
    """Validate the JSON Schema subset used by the snapshot contract."""
    errors = []
    kinds = schema.get("type")
    if kinds is not None:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        bool_ok = isinstance(value, bool) and "boolean" in kinds
        if not bool_ok and (isinstance(value, bool) or not any(isinstance(value, TYPES[k]) for k in kinds)):
            return [f"{path}: {type(value).__name__} not in {kinds}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match pattern")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}.{key}: required" for key in schema.get("required", []) if key not in value]
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                errors += schema_errors(item, props[key], f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}.{key}: not allowed")
            elif isinstance(extra, dict):
                errors += schema_errors(item, extra, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            errors.append(f"{path}: too many items")
        for index, item in enumerate(value):
            errors += schema_errors(item, schema.get("items", {}), f"{path}[{index}]")
    return errors


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = snapshot_cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class PrivacyFilterTests(unittest.TestCase):
    def test_only_allow_listed_flag_values_survive(self):
        flags = privacy_filter.sanitize_node_arguments([
            "--name", "my-host", "--node-key=abcd", "--validator", "--rpc-methods", "Safe",
            "--bootnodes", "/ip4/203.0.113.9/tcp/30333/p2p/12D3Koo", "--chain", "/home/alice/spec.json",
            "--state-pruning", "archive"])
        values = {f["flag"]: f["value"] for f in flags}
        self.assertEqual(values["--name"], "[redacted]")
        self.assertEqual(values["--node-key"], "[redacted]")
        self.assertEqual(values["--bootnodes"], "[redacted]")
        self.assertIs(values["--validator"], True)
        self.assertEqual(values["--rpc-methods"], "Safe")
        self.assertEqual(values["--chain"], "/home/~/spec.json")
        self.assertEqual(values["--state-pruning"], "archive")

    def test_sensitive_shapes_are_detected(self):
        samples = {"a": "0x" + "ab" * 32, "b": "addr 192.168.1.20", "c": "aa:bb:cc:dd:ee:ff",
                   "d": "Bearer abcdefghijk", "e": " ".join(["word"] * 12),
                   "f": "-----BEGIN OPENSSH PRIVATE KEY-----", "seedFile": "x"}
        found = privacy_filter.find_sensitive_content(samples)
        self.assertEqual(sorted(found), ["$.a", "$.b", "$.c", "$.d", "$.e", "$.f", "$.seedFile"])
        self.assertEqual(privacy_filter.find_sensitive_content({"sha256": "ab" * 32, "ver": "1.4.8"}), [])

    def test_mount_options_are_allow_listed(self):
        self.assertEqual(privacy_filter.filter_mount_options("rw,noatime,username=bob,errors=remount-ro"),
                         ["rw", "noatime"])


class ParserTests(unittest.TestCase):
    def test_bind_address_classes(self):
        classify = network_inventory.classify_bind_address
        self.assertEqual(classify("0100007F"), "loopback")
        self.assertEqual(classify("00000000"), "all-interfaces")
        self.assertEqual(classify("0101A8C0"), "specific-address")
        self.assertEqual(classify("0" * 32), "all-interfaces")
        self.assertEqual(classify("0" * 24 + "01000000"), "loopback")
        self.assertEqual(classify("0000000000000000FFFF00000100007F"), "loopback")

    def test_chrony_tracking_omits_reference_identity(self):
        tracking = ("Reference ID    : C0A80001 (192.168.0.1)\nStratum         : 3\n"
                    "System time     : 0.000020000 seconds slow of NTP time\nLeap status     : Normal\n")
        sources = ("MS Name/IP address  Stratum\n===============\n^* 10.0.0.1  2\n^+ 10.0.0.2  2\n^? 10.0.0.3 0\n")
        with patch.object(time_sync, "run_command", side_effect=[tracking, sources]):
            result = time_sync.collect_chrony(snapshot_cli.CollectionGaps())
        self.assertEqual(result["stratum"], 3)
        self.assertEqual(result["systemTimeOffsetSeconds"], -0.00002)
        self.assertEqual((result["sourcesTotal"], result["sourcesSelected"], result["sourcesCombined"],
                          result["sourcesUnreachable"]), (3, 1, 1, 1))
        self.assertNotIn("192.168", json.dumps(result))

    def test_rpc_summary_and_remote_refusal(self):
        replies = {"system_health": {"result": {"peers": 5, "isSyncing": False}},
                   "system_syncState": {"result": {"currentBlock": 10, "highestBlock": 12}},
                   "state_getRuntimeVersion": {"result": {"specName": "roko", "specVersion": 290}},
                   "temporal_getMeshState": {"error": {"code": -32601}}}
        summary = roko_rpc._summarize(replies, 9)
        self.assertEqual((summary["peers"], summary["currentBlock"], summary["specVersion"]), (5, 10, 290))
        self.assertIn("temporal_getMeshState", summary["unavailableMethods"])
        with self.assertRaises(roko_rpc.RpcEndpointRefused):
            roko_rpc.collect_rpc("https://rpc.example.org", 1, False, False, snapshot_cli.CollectionGaps())


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def live_snapshot(self, *extra):
        code, out, err = run_cli("--json", "--no-rpc", "--sample-seconds", "0.2",
                                 "--base-path", self.tmp.name, "--service", "roko-snapshot-test",
                                 "--process-name", "roko-snapshot-test", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_live_snapshot_matches_contract_and_is_value_free(self):
        snapshot = self.live_snapshot()
        self.assertEqual(schema_errors(snapshot, SCHEMA), [])
        self.assertIsNone(snapshot["identity"])
        self.assertEqual(privacy_filter.find_sensitive_content(snapshot), [])
        self.assertEqual({c["id"] for c in snapshot["checks"]} >= {"supported-architecture", "rpc-loopback-only"}, True)

    def test_identity_is_opt_in(self):
        snapshot = self.live_snapshot("--include-identity", "--label", "site-a.01")
        self.assertEqual(schema_errors(snapshot, SCHEMA), [])
        self.assertTrue(snapshot["identity"]["hostname"])
        self.assertEqual(snapshot["label"], "site-a.01")

    def test_refuses_to_emit_sensitive_content(self):
        leaked = {"host": {"note": "10.1.2.3"}}
        with patch.object(snapshot_cli, "collect_snapshot", return_value=leaked):
            code, out, err = run_cli("--json")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("$.host.note", err)

    def test_file_output_is_private_and_never_overwritten(self):
        target = os.path.join(self.tmp.name, "snap.json")
        args = ("--no-rpc", "--sample-seconds", "0", "--quiet", "--no-du", "--output", target)
        self.assertEqual(run_cli(*args)[0], 0)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        self.assertEqual(run_cli(*args)[0], 2)


class DocumentedCheckTests(unittest.TestCase):
    def test_archive_profile_and_exposed_rpc(self):
        snapshot = {
            "host": {"os": {"architecture": "aarch64", "id": "ubuntu", "idLike": "debian"}},
            "storage": {"dataFilesystem": {"availableBytes": 600 * 1024 ** 3}, "chainData": {"totalBytes": None}},
            "roko": {"service": {"present": True, "activeState": "active"},
                     "nodeFlags": {"flags": [{"flag": "--state-pruning", "value": "archive"},
                                             {"flag": "--rpc-methods", "value": "Unsafe"}]}},
            "network": {"listeners": [{"service": "rpc", "port": 9944, "protocol": "tcp",
                                       "bindScope": "all-interfaces"}]},
            "time": {"chrony": {"leapStatus": "Normal", "sourcesSelected": 1, "sourcesCombined": 0}},
            "node": {"reachable": False},
        }
        status = {c["id"]: c["status"] for c in documented_checks.evaluate_documented_checks(snapshot)}
        self.assertEqual(status, {"supported-architecture": "pass", "supported-distribution": "pass",
                                  "data-volume-allowance": "fail", "service-active": "pass",
                                  "rpc-methods-safe": "fail", "rpc-loopback-only": "fail",
                                  "clock-sources": "warn", "node-synced": "unknown"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
