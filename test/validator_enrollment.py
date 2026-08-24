#!/usr/bin/env python3
import argparse
import datetime as dt
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validator_enrollment", ROOT / "lib" / "validator_enrollment.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeRpc:
    def __init__(self, overrides=None):
        self.calls = []
        self.values = {
            ("chain_getBlockHash", (0,)): MODULE.TESTNET_GENESIS,
            ("system_chain", ()): "ROKO Testnet",
            ("state_getRuntimeVersion", ()): {"specName": "roko-testnet", "specVersion": 285, "transactionVersion": 4},
            ("state_getMetadata", ()): "0x01020304",
            ("system_health", ()): {"isSyncing": False, "peers": 4},
            ("system_localPeerId", ()): "12D3KooWValidatorCandidate",
            ("system_localListenAddresses", ()): ["/ip4/127.0.0.1/tcp/30333"],
            ("system_nodeRoles", ()): ["Full"],
            ("chain_getHeader", ()): {"number": "0x65"},
            ("chain_getFinalizedHead", ()): ["0xaaa", "0xbbb"],
            ("chain_getHeader", ("0xaaa",)): {"number": "0x63"},
            ("chain_getHeader", ("0xbbb",)): {"number": "0x64"},
            ("author_rotateKeys", ()): f"0x{'55' * 226}",
            ("author_hasSessionKeys", (f"0x{'55' * 226}",)): True,
        }
        if overrides:
            self.values.update(overrides)

    def call(self, method, params=None):
        key = (method, tuple(params or []))
        self.calls.append(key)
        value = self.values[key]
        if isinstance(value, list) and method == "chain_getFinalizedHead":
            return value.pop(0)
        return value


class ValidatorEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.binary = Path(self.temporary.name) / "roko-node"
        self.binary.write_text("#!/bin/sh\necho 'roko-node 1.1.0'\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.now = dt.datetime(2026, 8, 24, 16, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def args(self, **overrides):
        values = dict(
            rpc="http://127.0.0.1:9944",
            binary=str(self.binary),
            output=str(Path(self.temporary.name) / "enrollment.json"),
            expected_genesis=MODULE.TESTNET_GENESIS,
            public_address=["/dns4/validator.example/tcp/30333/p2p/12D3KooWValidatorCandidate"],
            minimum_peers=1,
            observation_seconds=0,
            expires_minutes=30,
            confirm_new_keys=True,
            session_keys=None,
        )
        values.update(overrides)
        return argparse.Namespace(**values)

    def build(self, rpc=None, args=None):
        return MODULE.build_enrollment(
            args or self.args(),
            rpc or FakeRpc(),
            observed_now=self.now,
            sleep=lambda _: None,
            clock_probe=lambda: True,
            listener_probe=lambda _: True,
            identifier=f"0x{'11' * 32}",
        )

    def test_builds_public_only_package_with_matching_digest(self):
        rpc = FakeRpc()
        package = self.build(rpc)
        self.assertEqual(package["schema"], MODULE.SCHEMA)
        self.assertEqual(package["network"]["specVersion"], 285)
        self.assertEqual(package["session"]["proofMode"], "legacy-empty")
        self.assertTrue(package["session"]["hasSessionKeys"])
        self.assertEqual(package["integrity"]["digest"], MODULE.canonical_digest(package))
        self.assertIn(("author_rotateKeys", ()), rpc.calls)
        self.assertNotRegex(json.dumps(package).lower(), r'"(?:seed|private|keystore|vault|token)"')

    def test_existing_keys_are_verified_without_rotating(self):
        keys = f"0x{'55' * 226}"
        rpc = FakeRpc()
        package = self.build(rpc, self.args(confirm_new_keys=False, session_keys=keys))
        self.assertEqual(package["session"]["encodedKeys"], keys)
        self.assertNotIn(("author_rotateKeys", ()), rpc.calls)

    def test_rejects_remote_rpc_authority_role_stale_finality_and_missing_custody(self):
        with self.assertRaisesRegex(MODULE.EnrollmentError, "loopback"):
            self.build(args=self.args(rpc="http://192.0.2.1:9944"))
        with self.assertRaisesRegex(MODULE.EnrollmentError, "non-authoring"):
            self.build(FakeRpc({("system_nodeRoles", ()): ["Authority"]}))
        with self.assertRaisesRegex(MODULE.EnrollmentError, "did not advance"):
            self.build(FakeRpc({
                ("chain_getFinalizedHead", ()): ["0xaaa", "0xaaa"],
                ("chain_getHeader", ("0xaaa",)): {"number": "0x63"},
            }))
        with self.assertRaisesRegex(MODULE.EnrollmentError, "custody"):
            self.build(FakeRpc({("author_hasSessionKeys", (f"0x{'55' * 226}",)): False}))

    def test_rejects_wrong_chain_sync_clock_and_public_listener(self):
        with self.assertRaisesRegex(MODULE.EnrollmentError, "Wrong genesis"):
            self.build(FakeRpc({("chain_getBlockHash", (0,)): f"0x{'99' * 32}"}))
        with self.assertRaisesRegex(MODULE.EnrollmentError, "synchronized"):
            self.build(FakeRpc({("system_health", ()): {"isSyncing": True, "peers": 4}}))
        with self.assertRaisesRegex(MODULE.EnrollmentError, "clock"):
            MODULE.build_enrollment(
                self.args(), FakeRpc(), observed_now=self.now, sleep=lambda _: None,
                clock_probe=lambda: False, listener_probe=lambda _: True,
            )
        with self.assertRaisesRegex(MODULE.EnrollmentError, "externally bound"):
            MODULE.build_enrollment(
                self.args(), FakeRpc(), observed_now=self.now, sleep=lambda _: None,
                clock_probe=lambda: True,
                listener_probe=lambda _: (_ for _ in ()).throw(MODULE.EnrollmentError("RPC port 9944 is externally bound")),
            )

    def test_detects_tamper_secret_field_and_replay_inputs(self):
        package = self.build()
        package["network"]["specVersion"] = 286
        with self.assertRaisesRegex(MODULE.EnrollmentError, "digest"):
            MODULE.validate_enrollment(package, self.now)
        package = self.build()
        package["walletSeed"] = "not-a-real-seed"
        with self.assertRaisesRegex(MODULE.EnrollmentError, "prohibited"):
            MODULE.validate_enrollment(package, self.now)
        package = self.build()
        with self.assertRaisesRegex(MODULE.EnrollmentError, "stale"):
            MODULE.validate_enrollment(package, self.now + dt.timedelta(days=1))

    def test_atomic_output_is_owner_only(self):
        package = self.build()
        output = Path(self.temporary.name) / "nested" / "enrollment.json"
        MODULE.atomic_write(output, package)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(json.loads(output.read_text())["integrity"], package["integrity"])


if __name__ == "__main__":
    unittest.main()
