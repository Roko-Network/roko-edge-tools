#!/usr/bin/env python3
"""Opt-in deployed validator-tool discovery and signed-release smoke test.

Run from any directory with ROKO_PUBLIC_CONTRACT=1. No privileged RPC or
credentials are used; the release installer is never executed by this test.
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://downloads.roko.network/validator-tools/current/"
INSTALL = BASE + "install-roko-validator-enroll.sh"
PAGES = {
    "nodes": "https://nodes.roko.network/validator/",
    "docs": "https://docs.roko.network/pages/prepare-validator.html",
    "agora": "https://agora.roko.network/participate/staking",
    "downloads": BASE,
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "roko-validator-public-contract/1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError(f"{url}: HTTP {response.status}")
        return response.read()


def main():
    if os.environ.get("ROKO_PUBLIC_CONTRACT") != "1":
        print("public contract skipped (set ROKO_PUBLIC_CONTRACT=1 to test deployment)")
        return 0
    failures = []
    for name, url in PAGES.items():
        try:
            page = fetch(url).decode("utf-8")
            if "roko-validator-enroll" not in page:
                failures.append(f"{name}: enrollment executable not discoverable")
            if INSTALL not in page and name != "downloads":
                failures.append(f"{name}: missing canonical signed install link {INSTALL}")
            if name == "downloads" and "install-roko-validator-enroll.sh" not in page:
                failures.append("downloads: installer absent from public listing")
        except (urllib.error.URLError, ValueError, UnicodeError) as error:
            failures.append(f"{name}: {error}")
    try:
        sums = fetch(BASE + "SHA256SUMS").decode("ascii")
        if not re.search(r"(?m)^[0-9a-f]{64} [ *]install-roko-validator-enroll\.sh$", sums):
            failures.append("downloads: installer absent from checksum manifest")
        entries = dict((name, digest) for digest, name in re.findall(r"(?m)^([0-9a-f]{64}) [ *](\S+)$", sums))
        installer = fetch(INSTALL)
        if hashlib.sha256(installer).hexdigest() != entries.get("install-roko-validator-enroll.sh"):
            failures.append("downloads: installer checksum differs from published manifest")
        metadata_name = next((name for name in entries
                              if re.fullmatch(r"roko-validator-enroll-[0-9]+\.[0-9]+\.[0-9]+\.metadata\.json", name)), None)
        if metadata_name is None:
            failures.append("downloads: versioned release metadata absent from checksum manifest")
        else:
            metadata_bytes = fetch(BASE + metadata_name)
            if hashlib.sha256(metadata_bytes).hexdigest() != entries[metadata_name]:
                failures.append("downloads: metadata checksum differs from published manifest")
            metadata = json.loads(metadata_bytes)
            artifact = metadata["artifact"]
            if metadata.get("package", {}).get("name") != metadata_name.removesuffix(".metadata.json"):
                failures.append("downloads: package name differs from versioned metadata name")
            archive = fetch(BASE + artifact["file"])
            if hashlib.sha256(archive).hexdigest() != entries.get(artifact["file"]):
                failures.append("downloads: archive checksum differs from published manifest")
            if len(archive) != artifact["bytes"] or hashlib.sha256(archive).hexdigest() != artifact["sha256"]:
                failures.append("downloads: archive size or SHA-256 differs from published metadata")
            if not re.fullmatch(r"[0-9a-f]{40}", metadata["source"]["revision"]):
                failures.append("downloads: source revision missing")
            if not metadata.get("updatedAt") or artifact.get("mediaType") != "application/gzip":
                failures.append("downloads: timestamp or media type missing")
        required_files = ["SHA256SUMS.asc", "roko-release-signing-key.asc", "install-roko-validator-enroll.sh"]
        if metadata_name:
            required_files.append(metadata_name + ".asc")
        for path in required_files:
            if not fetch(BASE + path):
                failures.append(f"downloads: empty {path}")
    except (urllib.error.URLError, ValueError, KeyError, TypeError, UnicodeError) as error:
        failures.append(f"downloads: {error}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if failures:
        return 1
    print("public validator enrollment contract ok (signature authenticity is verified by the signed installer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
