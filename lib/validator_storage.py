"""Substrate finalized storage key and vector decoding."""
import re
from validator_contract import ACCOUNT, EnrollmentError

MASK64 = (1 << 64) - 1

def _rotate_left(value: int, count: int) -> int:
    return ((value << count) | (value >> (64 - count))) & MASK64


def xxhash64(value: bytes, seed: int = 0) -> int:
    """Dependency-free xxHash64 used only to derive Substrate storage keys."""
    p1, p2, p3, p4, p5 = (11400714785074694791, 14029467366897019727, 1609587929392839161, 9650029242287828579, 2870177450012600261)
    index = 0
    if len(value) >= 32:
        lanes = [(seed + p1 + p2) & MASK64, (seed + p2) & MASK64, seed & MASK64, (seed - p1) & MASK64]
        while index <= len(value) - 32:
            for lane in range(4):
                word = int.from_bytes(value[index + lane * 8:index + lane * 8 + 8], "little")
                lanes[lane] = (_rotate_left((lanes[lane] + word * p2) & MASK64, 31) * p1) & MASK64
            index += 32
        result = sum(_rotate_left(lanes[lane], (1, 7, 12, 18)[lane]) for lane in range(4)) & MASK64
        for lane in lanes:
            mixed = (_rotate_left((lane * p2) & MASK64, 31) * p1) & MASK64
            result = ((result ^ mixed) * p1 + p4) & MASK64
    else:
        result = (seed + p5) & MASK64
    result = (result + len(value)) & MASK64
    while index <= len(value) - 8:
        word = int.from_bytes(value[index:index + 8], "little")
        mixed = (_rotate_left((word * p2) & MASK64, 31) * p1) & MASK64
        result = (_rotate_left(result ^ mixed, 27) * p1 + p4) & MASK64
        index += 8
    if index <= len(value) - 4:
        result = (_rotate_left(result ^ (int.from_bytes(value[index:index + 4], "little") * p1 & MASK64), 23) * p2 + p3) & MASK64
        index += 4
    while index < len(value):
        result = (_rotate_left(result ^ (value[index] * p5 & MASK64), 11) * p1) & MASK64
        index += 1
    result ^= result >> 33
    result = result * p2 & MASK64
    result ^= result >> 29
    result = result * p3 & MASK64
    return (result ^ (result >> 32)) & MASK64


def twox128(value: str) -> bytes:
    encoded = value.encode()
    return xxhash64(encoded, 0).to_bytes(8, "little") + xxhash64(encoded, 1).to_bytes(8, "little")


def storage_value_key(pallet: str, item: str) -> str:
    return "0x" + (twox128(pallet) + twox128(item)).hex()


def storage_map_key(pallet: str, item: str, account: str) -> str:
    if not ACCOUNT.fullmatch(account):
        raise EnrollmentError("Transition account must be a canonical 20-byte address")
    encoded = bytes.fromhex(account[2:])
    return "0x" + (twox128(pallet) + twox128(item) + xxhash64(encoded).to_bytes(8, "little") + encoded).hex()


def decode_compact_length(value: bytes) -> tuple[int, int]:
    if not value:
        raise EnrollmentError("Finalized storage returned an empty SCALE vector")
    mode = value[0] & 3
    if mode == 0:
        return value[0] >> 2, 1
    if mode == 1:
        if len(value) < 2: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
        return int.from_bytes(value[:2], "little") >> 2, 2
    if mode == 2:
        if len(value) < 4: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
        return int.from_bytes(value[:4], "little") >> 2, 4
    length = (value[0] >> 2) + 4
    if len(value) < 1 + length: raise EnrollmentError("Finalized storage contains a truncated SCALE vector")
    return int.from_bytes(value[1:1 + length], "little"), 1 + length


def decode_fixed_vector(raw: str | None, width: int) -> list[bytes]:
    if not isinstance(raw, str) or not re.fullmatch(r"0x(?:[0-9a-f]{2})*", raw, re.I):
        raise EnrollmentError("Finalized storage response is missing or malformed")
    value = bytes.fromhex(raw[2:])
    count, offset = decode_compact_length(value)
    if len(value) != offset + count * width:
        raise EnrollmentError("Finalized storage vector has an unexpected runtime shape")
    return [value[offset + index * width:offset + (index + 1) * width] for index in range(count)]


