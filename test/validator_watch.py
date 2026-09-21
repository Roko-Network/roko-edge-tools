#!/usr/bin/env python3

import contextlib
import importlib.machinery
import importlib.util
import io
import pathlib
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).parents[1] / "bin" / "roko-validator-watch"
LOADER = importlib.machinery.SourceFileLoader("roko_validator_watch", str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


def block_hash(block):
    return f"0x{block:064x}"


def authorship(block, authority=0):
    return {"blockNumber": block, "blockHash": block_hash(block), "authorityIndex": authority}


def observation(block, session=1, ready=True, mapped=2, contributing=2, proof=None, authority=0):
    return {
        "finalizedBlock": block,
        "readinessFinalizedBlock": block,
        "finalizedHash": block_hash(block),
        "sessionIndex": session,
        "candidateAccount": "0x" + "12" * 20,
        "activeBabeAuthorityIndex": authority,
        "lifecycleState": "ACTIVE_READY" if ready else "ACTIVE_INITIALIZING",
        "majorSyncing": False,
        "activeSessionMatch": True,
        "minimumTemporalSources": 2,
        "mappedTemporalPeers": mapped,
        "contributingTemporalPeers": contributing,
        "temporalTransportPeers": 2,
        "readyToAuthor": ready,
        "authorshipProof": proof,
        "authorshipProofCanonical": proof is not None,
        "remediation": "none" if ready else "wait",
    }


def response(*values):
    return [{"jsonrpc": "2.0", "id": index + 1, "result": value} for index, value in enumerate(values)]


class ValidatorWatchTests(unittest.TestCase):
    def test_fresh_canonical_authorship_in_ending_ready_window(self):
        proof = authorship(103)
        summary = MODULE.evaluate(
            [observation(100, ready=False), observation(102), observation(103, proof=proof)], 2, True)
        self.assertTrue(summary["passed"])
        self.assertTrue(summary["acceptancePassed"])
        self.assertEqual(summary["readyWindowFirstFinalizedBlock"], 102)
        self.assertEqual(summary["endingConsecutiveReadySamples"], 2)
        self.assertEqual(summary["authorshipProofs"], [proof])

    def test_stale_or_future_proof_does_not_prove_recovery(self):
        for height in (99, 100, 105):
            with self.subTest(height=height):
                summary = MODULE.evaluate([observation(100), observation(102, proof=authorship(height))], 2, True)
                self.assertFalse(summary["passed"])
                self.assertEqual(summary["authorshipProofs"], [])

    def test_first_readiness_height_is_freshness_baseline_despite_batch_race(self):
        first = observation(100)
        first["readinessFinalizedBlock"] = 102
        self.assertFalse(MODULE.evaluate([first, observation(103, proof=authorship(101))], 2, True)["passed"])

    def test_failed_tail_cannot_use_historical_ready_streak(self):
        samples = [observation(100), observation(101, proof=authorship(101)), observation(102, ready=False)]
        summary = MODULE.evaluate(samples, 2, True)
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["maximumConsecutiveReadySamples"], 2)
        self.assertEqual(summary["endingConsecutiveReadySamples"], 0)

    def test_readiness_restart_discards_old_window_proof(self):
        samples = [observation(100), observation(101, proof=authorship(101)),
                   observation(102, mapped=1), observation(103), observation(104, proof=authorship(101))]
        self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])

    def test_quorum_requires_positive_nonboolean_numbers(self):
        for field, value in [("minimumTemporalSources", 0), ("minimumTemporalSources", True),
                             ("minimumTemporalSources", -1), ("mappedTemporalPeers", True),
                             ("contributingTemporalPeers", "2"), ("mappedTemporalPeers", 2.0)]:
            with self.subTest(field=field, value=value):
                samples = [observation(100), observation(101, proof=authorship(101))]
                for item in samples:
                    item[field] = value
                self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])

    def test_nonmonotonic_or_inconsistent_finality_fails_even_if_end_advanced(self):
        for blocks in [(100, 99, 102), (100, 100, 100)]:
            with self.subTest(blocks=blocks):
                samples = [observation(n) for n in blocks]
                self.assertFalse(MODULE.evaluate(samples, 2, False)["passed"])
        samples = [observation(100), observation(100), observation(102)]
        samples[1]["finalizedHash"] = block_hash(999)
        self.assertFalse(MODULE.evaluate(samples, 2, False)["checks"]["finalityMonotonic"])
        samples = [observation(100), observation(102)]
        samples[1]["readinessFinalizedBlock"] = 99
        self.assertFalse(MODULE.evaluate(samples, 2, False)["passed"])

    def test_finality_must_advance_inside_ready_window(self):
        samples = [observation(99, ready=False), observation(100), observation(100)]
        self.assertFalse(MODULE.evaluate(samples, 2, False)["passed"])

    def test_candidate_change_or_missing_identity_cannot_pass(self):
        for candidate in [None, "", "0x" + "34" * 20]:
            with self.subTest(candidate=candidate):
                samples = [observation(100), observation(101, proof=authorship(101))]
                samples[-1]["candidateAccount"] = candidate
                self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])

    def test_authority_mismatch_and_unverified_proof_fail(self):
        for change in ["index", "canonical", "bool"]:
            with self.subTest(change=change):
                last = observation(101, proof=authorship(101))
                if change == "index":
                    last["authorshipProof"]["authorityIndex"] = 1
                elif change == "canonical":
                    last["authorshipProofCanonical"] = False
                else:
                    last["authorshipProof"]["authorityIndex"] = False
                self.assertFalse(MODULE.evaluate([observation(100), last], 2, True)["passed"])

    def test_index_change_across_session_is_valid_but_old_proof_is_not(self):
        samples = [observation(100), observation(101, session=2, authority=1),
                   observation(103, session=2, authority=1, proof=authorship(102, 1))]
        self.assertTrue(MODULE.evaluate(samples, 3, True, True)["passed"])
        samples[-1]["authorshipProof"] = authorship(101, 1)
        self.assertFalse(MODULE.evaluate(samples, 3, True, True)["passed"])

    def test_boundary_mode_requires_final_session_authorship(self):
        samples = [observation(100), observation(101, proof=authorship(101)),
                   observation(102, session=2, authority=1), observation(103, session=2, authority=1)]
        self.assertFalse(MODULE.evaluate(samples, 3, True, True)["passed"])
        self.assertFalse(MODULE.evaluate([observation(100), observation(101, proof=authorship(101))], 2, True, True)["passed"])

    def test_index_change_within_session_or_session_regression_fails(self):
        samples = [observation(100), observation(102, authority=1, proof=authorship(101, 1))]
        self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])
        samples = [observation(100, session=2), observation(102, session=1, proof=authorship(101))]
        self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])

    def test_invalid_sample_numbers_fail_closed(self):
        for field in ["finalizedBlock", "sessionIndex", "activeBabeAuthorityIndex", "readinessFinalizedBlock"]:
            with self.subTest(field=field):
                samples = [observation(100), observation(101, proof=authorship(101))]
                samples[-1][field] = True
                self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])

    def test_diagnostic_pass_is_never_acceptance(self):
        samples = [observation(100), observation(101)]
        self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])
        summary = MODULE.evaluate(samples, 2, False)
        self.assertTrue(summary["passed"])
        self.assertFalse(summary["acceptancePassed"])
        self.assertEqual(summary["mode"], "diagnostic-no-authorship")

    def test_sample_verifies_proof_with_safe_rpc_and_allowlists_proof(self):
        readiness = observation(103, proof={**authorship(102), "unexpected": "omit"})
        with patch.object(MODULE, "rpc_batch", side_effect=[
            response({"isSyncing": False}, block_hash(103), readiness, {}),
            response({"number": "0x67"}, block_hash(102)),
        ]) as rpc:
            item = MODULE.sample("http://unused", 1)
        self.assertTrue(item["authorshipProofCanonical"])
        self.assertNotIn("unexpected", item["authorshipProof"])
        self.assertEqual(rpc.call_args.args[2], [("chain_getHeader", [block_hash(103)]), ("chain_getBlockHash", [102])])

    def test_sample_rejects_noncanonical_or_unfinalized_proof(self):
        for canonical, finalized in [(block_hash(999), 103), (None, 103), (block_hash(102), 101)]:
            with self.subTest(canonical=canonical, finalized=finalized):
                with patch.object(MODULE, "rpc_batch", side_effect=[
                    response({}, block_hash(finalized), observation(finalized, proof=authorship(102)), {}),
                    response({"number": hex(finalized)}, canonical),
                ]):
                    self.assertFalse(MODULE.sample("http://unused", 1)["authorshipProofCanonical"])

    def test_cross_session_snapshot_race_cannot_accept_reused_index_proof(self):
        # The first head is from session1, but readiness is already in session2.
        # Proof at101 could be session1's different validator with index0.
        readiness = observation(102, session=2, proof=authorship(101))
        replies = [response({}, block_hash(100), readiness, {}),
                   response({"number": "0x64"}, block_hash(101))] * 3
        with patch.object(MODULE, "rpc_batch", side_effect=replies) as rpc:
            with self.assertRaisesRegex(ValueError, "all 3 attempts"):
                MODULE.sample("http://unused", 1)
        self.assertEqual(rpc.call_count, 6)

    def test_snapshot_race_retries_to_coherent_baseline(self):
        raced = observation(102, session=2, proof=authorship(101))
        coherent = observation(103, session=2, proof=authorship(101))
        replies = [response({}, block_hash(100), raced, {}),
                   response({"number": "0x64"}, block_hash(101)),
                   response({}, block_hash(103), coherent, {}),
                   response({"number": "0x67"}, block_hash(101))]
        with patch.object(MODULE, "rpc_batch", side_effect=replies):
            item = MODULE.sample("http://unused", 1)
        # Canonical alone is insufficient:101 precedes the coherent ready baseline.
        last = observation(104, session=2, proof=authorship(101))
        self.assertFalse(MODULE.evaluate([item, last], 2, True)["passed"])

    def test_malformed_rpc_shapes_raise_value_error(self):
        for value in [None, [], True, "ready"]:
            with self.subTest(value=value):
                with patch.object(MODULE, "rpc_batch", return_value=response({}, block_hash(100), value, {})):
                    with self.assertRaises(ValueError):
                        MODULE.sample("http://unused", 1)
        for batch in [[True], [{"id": True, "result": {}}], response({}) * 2, [{"id": 1}]]:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                MODULE.result(batch, 1)

    def test_malformed_readiness_fields_do_not_raise_unhandled_type_errors(self):
        for field, value in [("minimumTemporalSources", True), ("sessionIndex", []),
                             ("peerExclusions", "bad"), ("candidateAccount", {}),
                             ("authorshipProof", {"blockNumber": True}), ("readyToAuthor", 1),
                             ("genericP2pPeers", True), ("authoringTimeQuality", 1.5),
                             ("remediation", {"unsafe": "nested"})]:
            with self.subTest(field=field):
                readiness = observation(100)
                readiness[field] = value
                with patch.object(MODULE, "rpc_batch", side_effect=[
                    response({}, block_hash(100), readiness, {}), response({"number": "0x64"}),
                ]):
                    with self.assertRaises(ValueError):
                        MODULE.sample("http://unused", 1)

    def test_health_and_mesh_numeric_shapes_are_validated(self):
        for health, mesh in [({"peers": True}, {}), ({"isSyncing": 0}, {}),
                             ({}, {"peerCount": True}), ({}, {"timeQuality": "10000"})]:
            with self.subTest(health=health, mesh=mesh):
                with patch.object(MODULE, "rpc_batch", return_value=response(
                        health, block_hash(100), observation(100), mesh)):
                    with self.assertRaises(ValueError):
                        MODULE.sample("http://unused", 1)

    def test_cli_rejects_nonfinite_timing_and_impossible_sample_count(self):
        for args in [["--interval", "nan"], ["--timeout", "inf"], ["--timeout", "0"],
                     ["--samples", "2", "--require-consecutive-ready", "3"]]:
            with self.subTest(args=args), patch.object(MODULE.sys, "argv", [str(PATH)] + args):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    MODULE.main()
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
