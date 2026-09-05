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
from unittest import mock

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
        if isinstance(value, BaseException):
            raise value
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
            confirm_isolated_unsafe_rpc=True,
            session_keys=None,
            check_account=None,
            expected_session_keys=None,
            check_rpc_policy=False,
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

    def test_safe_rpc_rejection_is_actionable_and_distinct_from_other_failures(self):
        disabled = MODULE.RpcRejectedError(
            "author_rotateKeys", -32601, "RPC call is unsafe to be called externally"
        )
        with self.assertRaisesRegex(MODULE.EnrollmentError, "disabled by the node's Safe RPC policy"):
            self.build(FakeRpc({("author_rotateKeys", ()): disabled}))

        other = MODULE.RpcRejectedError("author_rotateKeys", -32000, "keystore unavailable")
        with self.assertRaisesRegex(MODULE.RpcRejectedError, "keystore unavailable"):
            self.build(FakeRpc({("author_rotateKeys", ()): other}))

        with self.assertRaisesRegex(MODULE.EnrollmentError, "confirm-isolated-unsafe-rpc"):
            self.build(args=self.args(confirm_isolated_unsafe_rpc=False))

    def test_non_mutating_rpc_policy_check_proves_safe_restoration(self):
        class PolicyRpc:
            def __init__(self, error=None):
                self.error = error
                self.calls = []

            def call(self, method, params=None):
                self.calls.append((method, tuple(params or [])))
                if method == "system_health":
                    return {"isSyncing": False, "peers": 3}
                if self.error:
                    raise self.error
                return False

        safe = PolicyRpc(MODULE.RpcRejectedError(
            "author_hasSessionKeys", -32601, "RPC call is unsafe to be called externally"
        ))
        report = MODULE.rpc_policy_status(safe)
        self.assertTrue(report["safeForNormalOperation"])
        self.assertEqual(report["state"], "safe-restored")
        self.assertEqual(safe.calls[-1], ("author_hasSessionKeys", ("0x",)))

        unsafe = MODULE.rpc_policy_status(PolicyRpc())
        self.assertFalse(unsafe["safeForNormalOperation"])
        self.assertEqual(unsafe["state"], "unsafe-key-management-accessible")

        with self.assertRaisesRegex(MODULE.EnrollmentError, "Unable to prove Safe RPC policy"):
            MODULE.rpc_policy_status(PolicyRpc(MODULE.RpcRejectedError(
                "author_hasSessionKeys", -32601, "Method not found"
            )))

    def test_rpc_client_preserves_structured_policy_rejection(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch.object(MODULE.urllib.request, "urlopen", return_value=response), \
             mock.patch.object(MODULE.json, "load", return_value={
                 "jsonrpc": "2.0",
                 "id": 1,
                 "error": {"code": -32601, "message": "RPC call is unsafe to be called externally"},
             }):
            with self.assertRaises(MODULE.RpcRejectedError) as observed:
                MODULE.RpcClient("http://127.0.0.1:9944").call("author_rotateKeys")
        self.assertEqual(observed.exception.code, -32601)
        self.assertTrue(MODULE.key_rpc_policy_disabled(observed.exception))

    def test_listener_classification_rejects_every_non_loopback_address(self):
        self.assertTrue(MODULE.listener_address_is_loopback("127.0.0.1:9944", 9944))
        self.assertTrue(MODULE.listener_address_is_loopback("[::1]:9944", 9944))
        for address in ("0.0.0.0:9944", "[::]:9944", "192.0.2.15:9944", "*:9944"):
            self.assertFalse(MODULE.listener_address_is_loopback(address, 9944))

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

    def test_substrate_storage_keys_and_finalized_transition_status(self):
        self.assertEqual(MODULE.storage_value_key("System", "Account")[:34], "0x26aa394eea5630e07c48ae0c9558cef7")
        account = f"0x{'22' * 20}"
        session_keys = f"0x{'55' * 226}"
        finalized = f"0x{'aa' * 32}"

        class TransitionRpc:
            def call(self, method, params=None):
                arguments = params or []
                if method == "chain_getFinalizedHead": return finalized
                if method == "chain_getHeader": return {"number": "0x64"}
                if method == "author_hasSessionKeys": return arguments == [session_keys]
                key = arguments[0]
                if key == MODULE.storage_value_key("Session", "Validators"):
                    return "0x04" + account[2:]
                present = {
                    MODULE.storage_map_key("Staking", "Bonded", account): f"0x{'33' * 20}",
                    MODULE.storage_map_key("Staking", "Validators", account): "0x0000000000",
                    MODULE.storage_map_key("Session", "NextKeys", account): session_keys,
                }
                return present.get(key)

        status = MODULE.check_transition(TransitionRpc(), account, session_keys)
        self.assertEqual(status["finalizedHeight"], "100")
        self.assertEqual(status["state"], "active")
        self.assertTrue(status["safeToEnableValidatorMode"])
        self.assertFalse(status["safeToRetireOldKeys"])

    def test_transition_check_fails_closed_on_key_or_runtime_shape_drift(self):
        account = f"0x{'22' * 20}"
        with self.assertRaisesRegex(MODULE.EnrollmentError, "canonical"):
            MODULE.storage_map_key("Session", "NextKeys", "not-an-account")
        with self.assertRaisesRegex(MODULE.EnrollmentError, "unexpected runtime shape"):
            MODULE.decode_fixed_vector("0x08" + account[2:], 20)


if __name__ == "__main__":
    unittest.main()
