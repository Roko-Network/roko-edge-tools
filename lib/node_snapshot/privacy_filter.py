"""Allow-list sanitizers and a final secret-shape scan for node snapshot output."""

from __future__ import annotations

import os
import re

# Node flags whose values are operationally useful and never secret or identifying.
# Every other flag is recorded by name only, with its value replaced.
VALUE_ALLOWED_FLAGS = frozenset({
    "--chain", "--pruning", "--state-pruning", "--blocks-pruning", "--rpc-methods",
    "--rpc-port", "--port", "--prometheus-port", "--database", "--db-cache",
    "--trie-cache-size", "--in-peers", "--in-peers-light", "--out-peers", "--sync",
    "--execution", "--wasm-execution", "--max-runtime-instances", "--rpc-max-connections",
    "--rpc-max-request-size", "--rpc-max-response-size", "--rpc-rate-limit", "--base-path",
    "--timing-profile", "--timesync-chrony-socket", "--timesync-participation-profile",
    "--timesync-convergence-threshold-ns", "--timesync-lucky-threshold-ns", "--log",
})
REDACTED = "[redacted]"
MAX_FLAGS = 128

MOUNT_OPTION_ALLOWED = re.compile(
    r"^(ro|rw|noatime|relatime|strictatime|lazytime|nodiratime|discard|nobarrier|barrier"
    r"|ssd|space_cache(=v\d)?|compress(-force)?=[a-z0-9:]+|commit=\d+|data=[a-z]+)$"
)

# Key names and value shapes that must never appear in a snapshot.
PROHIBITED_KEY = re.compile(
    r"(secret|private|seed|mnemonic|phrase|suri|keystore|vault|openbao|token|password"
    r"|cookie|approle|nodekey|serial|macaddr|ipaddr)", re.I)
SECRET_VALUE_PATTERNS = (
    re.compile(r"0x[0-9a-fA-F]{64}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"\b(?:[a-z]{3,8}\s+){11,}[a-z]{3,8}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b"),
)


def scrub_path(path: str | None) -> str | None:
    """Hide home-directory owner names in a filesystem path."""
    if path is None:
        return None
    return re.sub(r"^(/home|/Users)/[^/]+", r"\1/~", path).replace(os.path.expanduser("~"), "~")


def _clean_value(flag: str, value: str) -> str:
    if flag not in VALUE_ALLOWED_FLAGS:
        return REDACTED
    if flag in ("--chain", "--base-path", "--timesync-chrony-socket") and "/" in value:
        return scrub_path(value) or REDACTED
    return value[:128]


def sanitize_node_arguments(argv: list[str]) -> list[dict]:
    """Return [{flag, value}] for each --flag; values only for allow-listed flags."""
    flags: list[dict] = []
    index = 0
    while index < len(argv) and len(flags) < MAX_FLAGS:
        token = argv[index]
        index += 1
        if not token.startswith("--"):
            continue
        flag, has_inline, inline = token.partition("=")
        if has_inline:
            flags.append({"flag": flag, "value": _clean_value(flag, inline)})
        elif index < len(argv) and not argv[index].startswith("--"):
            flags.append({"flag": flag, "value": _clean_value(flag, argv[index])})
            index += 1
        else:
            flags.append({"flag": flag, "value": True})
    return flags


def flag_value(flags: list[dict], name: str):
    for entry in flags:
        if entry.get("flag") == name:
            return entry.get("value")
    return None


def filter_mount_options(options: str) -> list[str]:
    return [option for option in options.split(",") if MOUNT_OPTION_ALLOWED.match(option)]


def find_sensitive_content(document, path: str = "$") -> list[str]:
    """Return JSON paths whose key or string value looks secret or identifying."""
    findings: list[str] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if PROHIBITED_KEY.search(str(key)):
                findings.append(f"{path}.{key}")
            findings.extend(find_sensitive_content(value, f"{path}.{key}"))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            findings.extend(find_sensitive_content(value, f"{path}[{index}]"))
    elif isinstance(document, str):
        if any(pattern.search(document) for pattern in SECRET_VALUE_PATTERNS):
            findings.append(path)
    return findings
