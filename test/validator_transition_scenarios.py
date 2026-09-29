"""Issue #1 transition and rollback regression cases (public fixtures only)."""
import copy
import unittest
import __main__ as harness

MODULE = harness.MODULE
ACCOUNT = "0x" + "22" * 20
HEAD = "0x" + "aa" * 32
BLOCK = "0x" + "bb" * 32


class TransitionRpc:
    def __init__(self, report, keys, active=False, bonded=True, intent=True, account=ACCOUNT):
        self.report = report
        self.keys = keys
        self.active = active
        self.bonded = bonded
        self.intent = intent
        self.account = account
        self.calls = []

    def call(self, method, params=None):
        args = params or []
        self.calls.append((method, args))
        if method == "chain_getFinalizedHead": return HEAD
        if method == "chain_getHeader": return {"number": "0x64"}
        if method == "chain_getBlockHash": return MODULE.TESTNET_GENESIS if args == [0] else BLOCK
        if method == "state_getRuntimeVersion": return {"specName": "roko-testnet", "specVersion": 285}
        if method == "state_getMetadata": return "0x01020304"
        if method == "system_nodeRoles": return ["Authority"]
        if method == "author_hasSessionKeys": return args == [self.keys]
        if method == "temporal_getValidatorReadiness": return self.report
        if method == "state_getStorage":
            key = args[0]
            if key == MODULE.storage_value_key("Session", "Validators"):
                return "0x04" + self.account[2:] if self.active else "0x00"
            if key == MODULE.storage_map_key("Session", "NextKeys", self.account): return self.keys
            if key == MODULE.storage_map_key("Staking", "Bonded", self.account):
                return "0x01" if self.bonded else None
            if key == MODULE.storage_map_key("Staking", "Validators", self.account):
                return "0x00" if self.intent else None
            return None
        raise AssertionError(method)


class ValidatorTransitionScenarios(unittest.TestCase):
    def setUp(self):
        self.fixture = harness.ValidatorEnrollmentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.report = self.fixture.readiness()
        self.report["candidateAccount"] = ACCOUNT
        self.report["finalizedBlock"] = 100
        self.keys = "0x" + "".join(entry["expectedPublic"][2:] for entry in self.report["sessionKeys"])
        self.qualification = self.fixture.qualification()

    def check(self, active=False, submitted=None, account=ACCOUNT, **kwargs):
        rpc = TransitionRpc(self.report, self.keys, active=active, account=account, **kwargs)
        result = MODULE.check_transition(rpc, account, submitted or self.keys, self.qualification)
        self.assertEqual(MODULE.verify_receipt(result), result)
        return result

    def authored(self):
        self.report["authorshipProof"] = {"blockNumber": 99, "blockHash": BLOCK, "authorityIndex": 3}

    def test_registered_waiting_account_stale_temporal_key_regression(self):
        account = "0xA8128142dc3912334Bd4E03386742137b7E0B354"
        self.report["candidateAccount"] = account
        self.report["lifecycleState"] = "SESSION_KEYS_REGISTERED"
        self.report["queuedKeysMatch"] = False
        self.report["activeSessionMatch"] = False
        self.report["observedTemporalPublic"] = ["0x" + "ee" * 33]
        result = self.check(account=account)
        self.assertEqual(result["state"], "waiting")
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertTrue(any("Temporal public key mismatch" in stage for stage in result["failedStages"]))

    def test_stale_temporal_key(self):
        self.report["observedTemporalPublic"] = ["0x" + "ee" * 33]
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertTrue(any("Temporal public key mismatch" in stage for stage in result["failedStages"]))

    def test_wrong_tuple(self):
        wrong = "0x" + "ee" * 32 + self.keys[66:]
        result = self.check(submitted=wrong)
        self.assertFalse(result["sessionKeysMatch"])
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertEqual(result["evidence"]["submittedPublicTuple"], wrong)
        self.assertTrue(any("Session tuple mismatch" in stage for stage in result["failedStages"]))

    def test_queued_not_active(self):
        self.report["lifecycleState"] = "QUEUED"
        self.report["activeSessionMatch"] = False
        self.report["producerAuthorityIndex"] = None
        self.report["activeBabeAuthorityIndex"] = None
        self.report["activeTemporalAuthorityIndex"] = None
        result = self.check()
        self.assertTrue(result["safeToEnableValidatorMode"])
        self.assertFalse(result["safeToAuthor"])
        self.assertEqual(result["state"], "waiting")
        self.assertTrue(result["evidence"]["queuedKeysMatch"])

    def test_active_but_unmapped(self):
        self.authored()
        self.report["producerAuthorityIndex"] = None
        result = self.check(active=True)
        self.assertFalse(result["safeToAuthor"])
        self.assertTrue(any("Active authority mapping mismatch" in stage for stage in result["failedStages"]))

    def test_active_with_one_mapped_peer(self):
        self.authored()
        self.report["mappedTemporalPeers"] = 1
        result = self.check(active=True)
        self.assertFalse(result["safeToAuthor"])
        self.assertTrue(any("mapped active-authority" in stage for stage in result["failedStages"]))

    def test_two_ordinary_peers_zero_mapped_peers(self):
        self.report["genericP2pPeers"] = 2
        self.report["mappedTemporalPeers"] = 0
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertEqual(result["evidence"]["genericP2pPeers"], 2)
        self.assertEqual(result["evidence"]["mappedTemporalPeers"], 0)
        self.assertEqual(result["evidence"]["systemNodeRoles"], ["Authority"])

    def test_successful_activation(self):
        self.authored()
        result = self.check(active=True)
        self.assertTrue(result["safeToAuthor"])
        self.assertTrue(result["authorshipProven"])
        self.assertEqual(result["evidence"]["activeBabeAuthorityIndex"], 3)
        self.assertEqual(result["evidence"]["activeTemporalAuthorityIndex"], 3)

    def test_key_rotation(self):
        self.authored()
        old = self.check(active=True)
        self.report["sessionKeys"][-1]["expectedPublic"] = "0x" + "ee" * 33
        self.report["expectedTemporalPublic"] = "0x" + "ee" * 33
        self.report["observedTemporalPublic"] = ["0x" + "ee" * 33]
        rotated = self.check(active=True)
        self.assertTrue(old["authorshipProven"])
        self.assertFalse(rotated["safeToAuthor"])
        self.assertFalse(rotated["safeToRetireOldKeys"])
        self.assertNotEqual(old["integrity"], rotated["integrity"])

    def test_restart(self):
        self.authored()
        before = self.check(active=True)
        restarted_report = copy.deepcopy(self.report)
        self.report["authorshipProof"] = None
        after = self.check(active=True)
        self.assertTrue(before["safeToAuthor"])
        self.assertFalse(after["safeToAuthor"])
        self.report = restarted_report
        self.assertTrue(self.check(active=True)["safeToAuthor"])

    def test_rollback(self):
        self.authored()
        before = self.check(active=True)
        self.report["activeSessionMatch"] = False
        self.report["authorshipProof"] = None
        after = self.check(active=False)
        self.assertTrue(before["safeToAuthor"])
        self.assertFalse(after["safeToAuthor"])
        self.assertFalse(after["safeToRetireOldKeys"])

    def test_minimum_one_not_implicit_policy(self):
        self.report["minimumTemporalSources"] = 1
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertTrue(any("policy" in stage for stage in result["failedStages"]))

    def test_unsafe_remediation_text_rejected_without_echo(self):
        self.report["remediation"] = "Fixture location: /home/example/not-real"
        with self.assertRaisesRegex(MODULE.EnrollmentError, "unsafe explanatory text") as observed:
            self.check()
        self.assertNotIn("not-real", str(observed.exception))
        self.assertEqual(MODULE.bounded_rpc_message("Fixture location: /home/example/not-real"),
                         "RPC rejection (details redacted)")

    def test_receipt_tamper_and_qualification_drift(self):
        result = self.check()
        result["evidence"]["mappedTemporalPeers"] = 99
        with self.assertRaisesRegex(MODULE.EnrollmentError, "digest"):
            MODULE.verify_receipt(result)
        self.qualification["specVersion"] = 286
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertTrue(any("Qualification identity mismatch" in stage for stage in result["failedStages"]))

    def queued_set(self, keys=None, account=ACCOUNT, active=()):
        names = MODULE.KEY_TYPES
        key_types = ["gran", "babe", "imon", "audi", "mixn", "beef", "temp"]
        publics = [entry["expectedPublic"] for entry in self.report["sessionKeys"]] if keys is None else keys
        # account=None queues some other account (even with identical keys).
        self.report["queuedValidators"] = [{
            "account": "0x" + "33" * 20 if account is None else account,
            "matchesCandidate": account is not None and keys is None,
            "sessionKeys": [{"name": name, "keyType": key_type, "public": public}
                            for name, key_type, public in zip(names, key_types, publics)],
        }]
        self.report["activeValidators"] = list(active)

    def test_queued_set_present_and_matching_passes(self):
        self.queued_set(active=[ACCOUNT])
        result = self.check()
        self.assertTrue(result["safeToEnableValidatorMode"], result["failedStages"])
        evidence = result["evidence"]
        self.assertEqual(evidence["queuedSetEvidence"],
                         "Safe readiness RPC queuedValidators/activeValidators (raw public sets)")
        self.assertTrue(evidence["queuedTupleMatchesLocal"])
        self.assertTrue(evidence["candidateInReadinessActiveSet"])
        self.assertEqual(evidence["queuedCandidate"]["account"], ACCOUNT)
        self.assertEqual("0x" + "".join(key["public"][2:] for key in evidence["queuedCandidate"]["sessionKeys"]),
                         self.keys)

    def test_queued_set_mismatch_fails_with_named_key(self):
        publics = [entry["expectedPublic"] for entry in self.report["sessionKeys"]]
        publics[1] = "0x" + "ee" * 32
        self.queued_set(keys=publics)
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertFalse(result["evidence"]["queuedTupleMatchesLocal"])
        self.assertFalse(result["evidence"]["candidateInReadinessActiveSet"])
        stages = [stage for stage in result["failedStages"] if stage.startswith("Queued session tuple mismatch")]
        self.assertEqual(len(stages), 1)
        self.assertIn("queued public babe key(s) differ", stages[0])

    def test_queued_set_node_flag_mismatch_fails(self):
        self.queued_set()
        self.report["queuedValidators"][0]["matchesCandidate"] = False
        result = self.check()
        self.assertFalse(result["safeToEnableValidatorMode"])
        self.assertTrue(result["evidence"]["queuedTupleMatchesLocal"])
        self.assertTrue(any("queued entry does not match" in stage for stage in result["failedStages"]))

    def test_waiting_candidate_not_yet_queued_is_recorded_not_blocking(self):
        # Waiting (not yet elected) candidates are absent from the queued set;
        # the finalized nextKeys proof gates pre-activation, not queueing.
        self.queued_set(account=None)
        result = self.check()
        self.assertTrue(result["safeToEnableValidatorMode"], result["failedStages"])
        self.assertIsNone(result["evidence"]["queuedCandidate"])
        self.assertIsNone(result["evidence"]["queuedTupleMatchesLocal"])
        self.assertTrue(result["evidence"]["queuedSetEvidence"].endswith("candidate not yet queued"))

    def test_absent_queued_set_falls_back_unchanged(self):
        self.report["queuedKeysMatch"] = False
        result = self.check()
        self.assertTrue(result["safeToEnableValidatorMode"], result["failedStages"])
        evidence = result["evidence"]
        self.assertFalse(evidence["queuedKeysMatch"])
        self.assertEqual(evidence["queuedSetEvidence"], "unavailable (node predates readiness queued set)")
        self.assertIsNone(evidence["queuedCandidate"])
        self.assertIsNone(evidence["queuedTupleMatchesLocal"])
        self.assertIsNone(evidence["candidateInReadinessActiveSet"])
        self.assertFalse(any("queued" in stage.lower() for stage in result["failedStages"]))

    def test_queued_set_receipt_digest_deterministic_and_tamper_evident(self):
        self.queued_set(active=[ACCOUNT])
        first, second = self.check(), self.check()
        self.assertEqual(first, second)
        self.assertEqual(first["integrity"], second["integrity"])
        first["evidence"]["queuedCandidate"]["sessionKeys"][0]["public"] = "0x" + "ee" * 32
        with self.assertRaisesRegex(MODULE.EnrollmentError, "digest"):
            MODULE.verify_receipt(first)

    def test_queued_set_shape_is_validated(self):
        self.queued_set()
        del self.report["activeValidators"]
        with self.assertRaisesRegex(MODULE.EnrollmentError, "missing or unsupported"):
            MODULE.validate_readiness(self.report)
        self.queued_set()
        self.report["queuedValidators"][0]["sessionKeys"].reverse()
        with self.assertRaisesRegex(MODULE.EnrollmentError, "queued session-key ordering"):
            MODULE.validate_readiness(self.report)
        self.queued_set()
        self.report["queuedValidators"][0]["secretSeed"] = "not-real"
        with self.assertRaisesRegex(MODULE.EnrollmentError, "prohibited"):
            MODULE.validate_readiness(self.report)
