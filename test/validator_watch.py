#!/usr/bin/env python3

import importlib.machinery
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).parents[1] / "bin" / "roko-validator-watch"
LOADER = importlib.machinery.SourceFileLoader("roko_validator_watch", str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


def observation(block, session, ready, mapped=2, contributing=2, proof=None):
    return {
        "finalizedBlock": block,
        "sessionIndex": session,
        "lifecycleState": "ACTIVE_READY" if ready else "ACTIVE_INITIALIZING",
        "majorSyncing": False,
        "activeSessionMatch": True,
        "minimumTemporalSources": 2,
        "mappedTemporalPeers": mapped,
        "contributingTemporalPeers": contributing,
        "readyToAuthor": ready,
        "authorshipProof": proof,
        "remediation": "none" if ready else "wait",
    }


class ValidatorWatchTests(unittest.TestCase):
    def test_pass_requires_advancing_finality_ready_streak_and_authorship(self):
        proof = {"blockNumber": 103, "blockHash": "0xabc", "authorityIndex": 0}
        result = MODULE.evaluate(
            [observation(100, 1, False), observation(102, 1, True), observation(103, 1, True, proof=proof)],
            required_ready=2,
            require_authorship=True,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["maximumConsecutiveReadySamples"], 2)
        self.assertEqual(result["authorshipProofs"], [proof])

    def test_quorum_loss_resets_ready_streak(self):
        result = MODULE.evaluate(
            [observation(100, 1, True), observation(101, 1, True, mapped=1), observation(102, 2, True)],
            required_ready=2,
            require_authorship=False,
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["maximumConsecutiveReadySamples"], 1)

    def test_authorship_can_be_optional_for_diagnostic_windows(self):
        samples = [observation(100, 1, True), observation(101, 1, True)]
        self.assertFalse(MODULE.evaluate(samples, 2, True)["passed"])
        self.assertTrue(MODULE.evaluate(samples, 2, False)["passed"])


if __name__ == "__main__":
    unittest.main()
