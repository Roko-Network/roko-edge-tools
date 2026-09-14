#!/usr/bin/env python3
"""Opt-in policy probe qualification of an exact node binary on a disposable chain.

No enrollment or key RPC writes. Does not qualify successful package generation.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def qualify(binary):
    observations = []
    with tempfile.TemporaryDirectory(prefix="roko-policy-", dir="/dev/shm") as directory:
        for mode, expected in (("Safe", 0), ("Unsafe", 2), ("Safe", 0)):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            url = f"http://127.0.0.1:{port}"

            def rpc(method, params=None):
                request = urllib.request.Request(url, data=json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": method, "params": params or [],
                }).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    return json.load(response)

            with open(directory + "/node.log", "w+") as log:
                process = subprocess.Popen([
                    str(binary), "--chain", "local_testnet", "--base-path", directory + "/db",
                    "--rpc-port", str(port), "--rpc-methods", mode, "--no-mdns", "--no-telemetry",
                    "--in-peers", "0", "--out-peers", "0", "--reserved-only",
                    "--listen-addr", "/ip4/127.0.0.1/tcp/0", "--offchain-worker", "never",
                    "--no-prometheus",
                ], stdout=log, stderr=log)
                try:
                    for _ in range(60):
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError("Node exited: " + log.read()[-2000:])
                        try:
                            health = rpc("system_health")
                            break
                        except OSError:
                            time.sleep(0.5)
                    else:
                        raise RuntimeError("RPC startup timeout")
                    roles = rpc("system_nodeRoles")
                    assert roles["result"] == ["Full"], roles
                    assert health["result"]["peers"] == 0, health
                    row = {
                        "mode": mode, "version": rpc("system_version"), "roles": roles,
                        "emptyTuple": rpc("author_hasSessionKeys", ["0x"]),
                        "dummyKey": rpc("author_hasKey", ["0x" + "00" * 32, "babe"]),
                    }
                    result = subprocess.run([
                        str(ROOT / "bin/roko-validator-enroll"), "--rpc", url, "--check-rpc-policy",
                    ], capture_output=True, text=True, timeout=15)
                    row["cliExit"] = result.returncode
                    row["cliOutput"] = json.loads(result.stdout) if result.stdout else result.stderr
                    observations.append(row)
                    assert result.returncode == expected, row
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "observedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "binaryVersion": subprocess.check_output([str(binary), "--version"], text=True).strip(),
        "binarySha256": digest,
        "scope": "Disposable local_testnet Full node; zero peers; loopback listeners; read-only key probes",
        "observations": observations, "processesStopped": True, "temporaryStateRemoved": True,
        "guardedGenerationQualified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.binary.resolve()), indent=2))
