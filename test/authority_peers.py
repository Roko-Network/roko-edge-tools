#!/usr/bin/env python3
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("authority_peers", ROOT / "lib" / "authority_peers.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class AuthorityPeerTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 6, 15, 0, tzinfo=dt.timezone.utc)
        self.apps02 = "12D3KooWDwrPobC2ZpmjYJwgTFpCd7uyaeqXu1FQctmsdKffsmwN"
        self.titan = "12D3KooWFXjLThfEcwWj6T5E8ir1PAVGSgMgmpPjXBSQuXWvAz5y"
        self.value = {
            "schema": MODULE.SCHEMA,
            "network": MODULE.NETWORK,
            "generatedAt": "2026-09-06T14:55:00Z",
            "expiresAt": "2026-09-13T14:55:00Z",
            "finalized": {
                "blockNumber": 1036236,
                "blockHash": "0x" + "ab" * 32,
                "sessionIndex": 965,
            },
            "minimumMappedPeers": 2,
            "authorities": [
                {
                    "account": "0xc04c98d1cd1ff5f6611a8bd413d09d03bd3f4a89",
                    "peerId": self.apps02,
                    "addresses": [f"/ip4/66.94.104.190/tcp/30334/p2p/{self.apps02}"],
                },
                {
                    "account": "0x1efd476f84b8198123c218710630916faaf394ec",
                    "peerId": self.titan,
                    "addresses": [f"/ip4/66.94.104.190/tcp/30335/p2p/{self.titan}"],
                },
            ],
        }

    def test_accepts_exact_fresh_public_active_authority_contract(self):
        self.assertEqual(MODULE.validate_manifest(self.value, self.now), self.value)

    def test_rejects_private_address_peer_mismatch_expiry_and_lowered_gate(self):
        private = json.loads(json.dumps(self.value))
        private["authorities"][0]["addresses"] = [f"/ip4/10.0.42.111/tcp/30333/p2p/{self.apps02}"]
        with self.assertRaisesRegex(MODULE.AuthorityPeerError, "private"):
            MODULE.validate_manifest(private, self.now)
        mismatch = json.loads(json.dumps(self.value))
        mismatch["authorities"][0]["addresses"] = [f"/ip4/66.94.104.190/tcp/30334/p2p/{self.titan}"]
        with self.assertRaisesRegex(MODULE.AuthorityPeerError, "mismatched"):
            MODULE.validate_manifest(mismatch, self.now)
        expired = json.loads(json.dumps(self.value))
        expired["expiresAt"] = "2026-09-06T14:59:59Z"
        with self.assertRaisesRegex(MODULE.AuthorityPeerError, "expired"):
            MODULE.validate_manifest(expired, self.now)
        lowered = json.loads(json.dumps(self.value))
        lowered["minimumMappedPeers"] = 1
        with self.assertRaisesRegex(MODULE.AuthorityPeerError, "two-mapped-peer"):
            MODULE.validate_manifest(lowered, self.now)

    def test_atomic_output_is_canonical_owner_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "authority-peers.json"
            MODULE.atomic_write(output, self.value)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text()), self.value)


if __name__ == "__main__":
    unittest.main()
