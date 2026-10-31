"""Bounded, unprivileged probe helpers that record collection gaps instead of failing."""

from __future__ import annotations

import os
import shutil
import subprocess

# Children get a minimal environment: parseable C-locale output and no inherited
# operator variables (which could hold credentials).
CHILD_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
    "LC_ALL": "C",
}


class CollectionGaps:
    """Ordered list of probes that could not be collected, with a short reason."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, area: str, reason: str) -> None:
        entry = {"area": area, "reason": reason}
        if entry not in self.items:
            self.items.append(entry)


def read_text(path: str, gaps: CollectionGaps | None = None, area: str | None = None,
              limit: int = 262144) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit).replace("\x00", " ").strip()
    except OSError as error:
        if gaps is not None and area:
            gaps.add(area, f"unreadable ({type(error).__name__})")
        return None


def read_int(path: str) -> int | None:
    text = read_text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def run_command(argv: list[str], timeout: float = 10.0, ok_codes: tuple = (0,)) -> str | None:
    """Run a read-only command; return stdout, or None if missing, failing or slow."""
    if shutil.which(argv[0]) is None and not os.path.isabs(argv[0]):
        return None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                check=False, env=CHILD_ENV, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in ok_codes:
        return None
    return result.stdout


def parse_key_values(text: str | None, separator: str = "=") -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        if separator in line:
            key, value = line.split(separator, 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
