"""Minimal SNTP client: measure stratum, round-trip delay and offset to one NTP server."""

from __future__ import annotations

import os
import socket
import struct
import time

NTP_PORT = 123
NTP_EPOCH_OFFSET = 2208988800
PACKET = struct.Struct("!BBbbII4sQQQQ")
CLIENT_HEADER = (0 << 6) | (4 << 3) | 3  # leap 0, version 4, mode 3 (client)
SERVER_MODE = 4
LEAP_ALARM = 3
KISS_CODES = {b"RATE", b"DENY", b"RSTR"}


class ProbeRejected(Exception):
    """The server answered, but the reply must not be used (and may ask us to stop)."""

    def __init__(self, reason: str, stop: bool = False):
        super().__init__(reason)
        self.reason, self.stop = reason, stop


def _to_ntp(seconds: float) -> int:
    whole = int(seconds) + NTP_EPOCH_OFFSET
    return (whole << 32) | int((seconds % 1) * (1 << 32))


def _from_ntp(value: int) -> float:
    return (value >> 32) - NTP_EPOCH_OFFSET + (value & 0xFFFFFFFF) / (1 << 32)


def resolve(host: str, port: int = NTP_PORT) -> tuple:
    family, _, _, _, address = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)[0]
    return family, address


def query_once(family: int, address: tuple, timeout: float) -> dict:
    """Send one client request; return stratum, leap, delay and offset in seconds."""
    # A random transmit timestamp makes the origin check meaningful against spoofed replies.
    sent = time.time()
    origin = _to_ntp(sent) ^ int.from_bytes(os.urandom(2), "big")
    request = PACKET.pack(CLIENT_HEADER, 0, 0, 0, 0, 0, b"\0" * 4, 0, 0, 0, origin)
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        t1 = time.time()
        sock.sendto(request, address)
        data, _ = sock.recvfrom(512)
        t4 = time.time()
    return parse_reply(data, origin, t1, t4)


def parse_reply(data: bytes, origin: int, t1: float, t4: float) -> dict:
    if len(data) < PACKET.size:
        raise ProbeRejected("short reply")
    header, stratum, _, _, _, _, refid, _, echoed, receive, transmit = PACKET.unpack(data[:PACKET.size])
    leap, mode = header >> 6, header & 0x7
    if echoed != origin:
        raise ProbeRejected("origin timestamp mismatch")
    if stratum == 0:
        code = refid.rstrip(b"\0")
        raise ProbeRejected(f"kiss-o'-death {code.decode('ascii', 'replace')}", stop=code in KISS_CODES)
    if mode != SERVER_MODE or not transmit:
        raise ProbeRejected("not a server reply")
    t2, t3 = _from_ntp(receive), _from_ntp(transmit)
    return {"stratum": stratum, "leap": leap,
            "delay": (t4 - t1) - (t3 - t2), "offset": ((t2 - t1) + (t3 - t4)) / 2}
