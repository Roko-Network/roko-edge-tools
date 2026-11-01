#!/usr/bin/env python3
"""Tests for roko-stratum1-select: SNTP parsing, polite ranking, diversity and Chrony output."""

import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from stratum1_select import candidate_ranking, chrony_sources, ntp_probe  # noqa: E402


class FakeNtpServer:
    """UDP server on loopback answering like an NTP server with a configurable reply."""

    def __init__(self, stratum=1, leap=0, refid=b"GPS\0", corrupt_origin=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.stratum, self.leap, self.refid, self.corrupt = stratum, leap, refid, corrupt_origin
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                data, peer = self.sock.recvfrom(512)
            except OSError:
                return
            origin = ntp_probe.PACKET.unpack(data[:48])[-1]
            now = ntp_probe._to_ntp(time.time())
            header = (self.leap << 6) | (4 << 3) | 4
            echoed = origin ^ 1 if self.corrupt else origin
            self.sock.sendto(ntp_probe.PACKET.pack(header, self.stratum, 6, -20, 0, 0, self.refid,
                                                   now, echoed, now, now), peer)

    def close(self):
        self.sock.close()

    @property
    def target(self):
        return f"127.0.0.1:{self.port}"


def measure(server, samples=2):
    return candidate_ranking.summarize(candidate_ranking.measure_candidate(
        {"host": server.target, "operator": "test", "region": None}, samples, 0.01, 1.0))


class ProbeTests(unittest.TestCase):
    def test_stratum1_reply_is_measured(self):
        server = FakeNtpServer()
        self.addCleanup(server.close)
        result = measure(server)
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["stratum"], 1)
        self.assertLess(result["minDelayMs"], 50)
        self.assertLess(abs(result["offsetMs"]), 50)

    def test_kiss_of_death_stops_and_disqualifies(self):
        server = FakeNtpServer(stratum=0, refid=b"RATE")
        self.addCleanup(server.close)
        raw = candidate_ranking.measure_candidate({"host": server.target, "operator": "t", "region": None}, 4, 0.01, 1.0)
        self.assertEqual(len(raw["errors"]), 1, "must stop after a RATE kiss")
        self.assertFalse(candidate_ranking.summarize(raw)["eligible"])

    def test_spoofed_origin_and_stratum2_and_leap_alarm_are_rejected(self):
        for kwargs, reason in (({"corrupt_origin": True}, "too few usable replies"),
                               ({"stratum": 2}, "not stratum 1"),
                               ({"leap": 3}, "too few usable replies")):
            server = FakeNtpServer(**kwargs)
            self.addCleanup(server.close)
            result = measure(server)
            self.assertFalse(result["eligible"], kwargs)
            self.assertEqual(result["reason"], reason)

    def test_unresolvable_host(self):
        raw = candidate_ranking.measure_candidate({"host": "nonexistent.invalid", "operator": "t", "region": None}, 2, 0.01, 0.5)
        self.assertEqual(raw["errors"], ["name does not resolve"])


class SelectionTests(unittest.TestCase):
    def ranked(self):
        rows = [("a1", "A", 10), ("a2", "A", 11), ("b1", "B", 80), ("c1", "C", 90)]
        return [{"host": h, "operator": o, "eligible": True, "minDelayMs": d} for h, o, d in rows] + \
               [{"host": "x", "operator": "X", "eligible": False, "reason": "not stratum 1"}]

    def test_prefers_operator_diversity_then_distance(self):
        self.assertEqual([c["host"] for c in candidate_ranking.choose_sources(self.ranked(), 2)], ["a1", "b1"])
        self.assertEqual([c["host"] for c in candidate_ranking.choose_sources(self.ranked(), 4)], ["a1", "b1", "c1", "a2"])

    def test_render_prefers_only_the_nearest(self):
        chosen = candidate_ranking.choose_sources(self.ranked(), 2)
        text = chrony_sources.render_sources(chosen, "2026-10-31T00:00:00Z", "1.4.8")
        self.assertIn("server a1 iburst prefer minpoll 6 maxpoll 10", text)
        self.assertIn("server b1 iburst minpoll 6 maxpoll 10", text)
        self.assertEqual(text.count("prefer"), 1)


class InstallTests(unittest.TestCase):
    def test_sourcedir_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = os.path.join(tmp, "chrony.conf")
            Path(conf).write_text("pool x iburst\n  sourcedir /etc/chrony/sources.d\n")
            self.assertEqual(chrony_sources.find_sourcedir([conf]), "/etc/chrony/sources.d")
            Path(conf).write_text("pool x iburst\n#sourcedir /nope\n")
            self.assertIsNone(chrony_sources.find_sourcedir([conf, os.path.join(tmp, "missing")]))

    def test_install_refuses_without_root_or_sourcedir(self):
        with patch.object(chrony_sources.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(chrony_sources.InstallBlocked, "needs root"):
                chrony_sources.install_sources("x", ["a"], "/tmp")
        with patch.object(chrony_sources.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(chrony_sources.InstallBlocked, "sourcedir"):
                chrony_sources.install_sources("x", ["a"], None)

    def test_write_is_atomic_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sources.d", "roko-stratum1.sources")
            self.assertIsNone(chrony_sources._write_atomic(path, "one\n"))
            backup = chrony_sources._write_atomic(path, "two\n")
            self.assertEqual((Path(path).read_text(), Path(backup).read_text()), ("two\n", "one\n"))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o644)


class CatalogTests(unittest.TestCase):
    def test_catalog_shape(self):
        import json
        catalog = json.loads((Path(__file__).resolve().parents[1] / "installer" / "stratum1-candidates.json").read_text())
        self.assertEqual(catalog["schema"], "roko.stratum1-candidates.v1")
        hosts = [c["host"] for c in catalog["candidates"]]
        self.assertEqual(len(hosts), len(set(hosts)))
        for entry in catalog["candidates"]:
            self.assertEqual(set(entry), {"host", "operator", "region", "directory"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
