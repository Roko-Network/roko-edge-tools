#!/usr/bin/env python3
"""Opt-in native/systemd guarded-enrollment qualification on a disposable chain.

Requires local passwordless sudo for a uniquely named temporary service. Uses
only development authorities and tmpfs state; never connects to public peers.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL_BIN = ROOT / "bin"
LIVE_GENESIS = "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, capture_output=True, text=True,
                          timeout=kwargs.pop("timeout", 30), **kwargs)


def rpc(port, method, params=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}", data=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or [],
    }).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3) as response:
        result = json.load(response)
    if "error" in result:
        raise ValueError(f"{method}: {result['error']}")
    return result["result"]


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_rpc(rpc_port, alive):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if not alive():
            raise RuntimeError("owned node exited before RPC startup")
        try:
            return rpc(rpc_port, "chain_getBlockHash", [0])
        except (OSError, ValueError):
            time.sleep(1)
    raise TimeoutError("RPC startup deadline")


def qualify(binary, expected, receipt, runtime_wasm, expected_runtime, runtime_spec, agora_module=None, agora_sha256=None):
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError("binary digest mismatch")
    runtime_code = runtime_wasm.read_bytes()
    if hashlib.sha256(runtime_code).hexdigest() != expected_runtime:
        raise ValueError("runtime digest mismatch")
    if receipt.exists():
        raise ValueError("receipt already exists")
    if bool(agora_module) != bool(agora_sha256):
        raise ValueError("Agora module path and digest must be supplied together")
    if agora_module and hashlib.sha256(agora_module.read_bytes()).hexdigest() != agora_sha256:
        raise ValueError("Agora module digest mismatch")
    run("sudo", "-n", "true")
    if run("timedatectl", "show", "-p", "NTPSynchronized", "--value").stdout.strip() != "yes":
        raise ValueError("host clock is not synchronized")
    name = "roko-enrollment-qualification-" + uuid.uuid4().hex[:12]
    unit = name + ".service"
    unit_path = Path("/run/systemd/system") / unit
    report = {"runId": name, "status": "incomplete", "binarySha256": digest,
              "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "binaryVersion": run(str(binary), "--version").stdout.strip(),
              "toolVersion": run(str(TOOL_BIN / "roko-validator-enroll"), "--version").stdout.strip(),
              "installedCommandLinks": (TOOL_BIN / "roko-session-key-window").is_symlink(),
              "helperSha256": hashlib.sha256((TOOL_BIN / "roko-session-key-window").read_bytes()).hexdigest(),
              "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "service": unit, "liveChainUsed": False, "authorityPolicy": "development log-only",
              "runtimeCodeSha256": expected_runtime, "expectedRuntimeSpec": runtime_spec}
    processes, logs = [], []
    installed = False
    try:
        with tempfile.TemporaryDirectory(prefix=name + "-", dir="/dev/shm") as directory:
            root = Path(directory)
            try:
                spec = json.loads(run(str(binary), "build-spec", "--chain", "dev", "--raw",
                                      "--disable-default-bootnode", timeout=90).stdout)
                spec["bootNodes"] = []
                spec["telemetryEndpoints"] = None
                # Preserve development accounts/authority state, use the exact
                # separately verified runtime. This is never the live genesis.
                if "0x3a636f6465" not in spec["genesis"]["raw"]["top"]:
                    raise ValueError("raw development spec lacks runtime code")
                spec["genesis"]["raw"]["top"]["0x3a636f6465"] = "0x" + runtime_code.hex()
                spec_path = root / "chain.json"
                spec_path.write_text(json.dumps(spec))
                peers = []

                def command(role, rpc_port, p2p_port):
                    # Public, predictable development identities only. As in the
                    # core qualification harness, provide them through files;
                    # validators deliberately refuse implicit key generation.
                    fixture_key = root / (role + "-node-key")
                    fixture_key.write_bytes((1 + ("alice", "bob", "charlie", "candidate").index(role)).to_bytes(32, "big"))
                    fixture_key.chmod(0o600)
                    return [str(binary), "--chain", str(spec_path), "--base-path", str(root / role),
                            "--node-key-file", str(fixture_key),
                            "--rpc-port", str(rpc_port), "--listen-addr", f"/ip4/127.0.0.1/tcp/{p2p_port}",
                            "--no-mdns", "--no-telemetry", "--no-prometheus",
                            "--out-peers", "0", "--in-peers", "4",
                            "--allow-private-ip", "--offchain-worker", "never", "--timesync-no-enforce",
                            "--db-storage-threshold", "0"]

                for role in ("alice", "bob", "charlie"):
                    rpc_port, p2p_port = port(), port()
                    log = (root / (role + ".log")).open("w+")
                    logs.append(log)
                    args = command(role, rpc_port, p2p_port) + ["--validator", "--" + role,
                                                               "--rpc-methods", "Safe"]
                    if peers:
                        args += ["--reserved-nodes", *peers]
                    process = subprocess.Popen(args, stdout=log, stderr=log)
                    processes.append(process)
                    try:
                        genesis = wait_rpc(rpc_port, lambda: process.poll() is None)
                    except Exception:
                        log.flush()
                        log.seek(0)
                        report["startupDiagnostic"] = {"role": role, "exit": process.poll(),
                                                       "logTail": log.read()[-3000:]}
                        raise
                    if genesis == LIVE_GENESIS:
                        raise ValueError("refusing live genesis")
                    if report.setdefault("genesis", genesis) != genesis:
                        raise ValueError("development genesis mismatch")
                    peers.append(f"/ip4/127.0.0.1/tcp/{p2p_port}/p2p/{rpc(rpc_port, 'system_localPeerId')}")

                rpc_port, p2p_port = port(), port()
                policy = root / "node-rpc.env"
                initial = root / "initial-policy"
                initial.write_text("ROKO_RPC_METHODS=Safe\n")
                run("sudo", "-n", "install", "-m", "0600", str(initial), str(policy))
                user = pwd.getpwuid(os.getuid()).pw_name
                args = command("candidate", rpc_port, p2p_port)
                args += ["--rpc-methods", "${ROKO_RPC_METHODS}", "--reserved-nodes", *peers]
                # All generated paths contain no whitespace or shell metacharacters.
                if any(any(c.isspace() for c in arg) for arg in args):
                    raise ValueError("unit argument requires unsupported quoting")
                source = root / unit
                startup_gate = root / "startup-gate"
                fail_start = root / "fail-unsafe-start"
                startup_gate.write_text('#!/bin/sh\nif [ -f "' + str(fail_start) +
                                        '" ] && [ "$ROKO_RPC_METHODS" = Unsafe ]; then exit 1; fi\n')
                startup_gate.chmod(0o755)
                source.write_text("[Unit]\nDescription=Disposable ROKO enrollment qualification\n"
                                  "[Service]\nType=simple\nUser=" + user + "\n"
                                  "Environment=ROKO_RPC_METHODS=Safe\nEnvironmentFile=-" + str(policy) + "\n"
                                  "ExecStartPre=" + str(startup_gate) + "\n"
                                  "ExecStart=" + " ".join(args) + "\nRestart=no\nNoNewPrivileges=yes\n"
                                  "TimeoutStopSec=15\nStandardOutput=append:" + str(root / "candidate.log") + "\n"
                                  "StandardError=inherit\n")
                if unit_path.exists():
                    raise ValueError("unit already exists")
                run("sudo", "-n", "install", "-m", "0644", str(source), str(unit_path))
                installed = True
                run("sudo", "-n", "systemctl", "daemon-reload")
                run("sudo", "-n", "systemctl", "start", unit)
                genesis = wait_rpc(rpc_port, lambda: subprocess.run(
                    ["systemctl", "is-active", "--quiet", unit]).returncode == 0)
                if genesis != report["genesis"]:
                    raise ValueError("candidate genesis mismatch")
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    head = rpc(rpc_port, "chain_getFinalizedHead")
                    height = int(rpc(rpc_port, "chain_getHeader", [head])["number"], 16)
                    health = rpc(rpc_port, "system_health")
                    if height >= 5 and not health["isSyncing"] and health["peers"] >= 2:
                        break
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError("owned authority exited")
                    time.sleep(2)
                else:
                    report["lastHealth"] = health
                    report["lastFinalizedHeight"] = height
                    raise TimeoutError("candidate finality/sync deadline")
                report["before"] = {"finalizedHeight": height, "health": health,
                                    "roles": rpc(rpc_port, "system_nodeRoles"),
                                    "runtime": rpc(rpc_port, "state_getRuntimeVersion")}
                if report["before"]["roles"] != ["Full"]:
                    raise ValueError("candidate must be non-authoring")
                if report["before"]["runtime"]["specVersion"] != runtime_spec:
                    raise ValueError("candidate runtime mismatch")
                output = root / "package.json"
                peer = rpc(rpc_port, "system_localPeerId")
                result = run("sudo", "-n", str(TOOL_BIN / "roko-session-key-window"),
                             "--service", unit, "--policy-file", str(policy),
                             "--rpc", f"http://127.0.0.1:{rpc_port}",
                             "--confirm-isolated-window", "--confirm-no-forwarding", "--",
                             "--binary", str(binary), "--expected-genesis", genesis,
                             "--minimum-peers", "2", "--observation-seconds", "8",
                             "--public-address", f"/ip4/127.0.0.1/tcp/{p2p_port}/p2p/{peer}",
                             "--output", str(output), timeout=180)
                report["helperExit"] = result.returncode
                package = json.loads(run("sudo", "-n", "cat", str(output)).stdout)
                # Retain only qualification facts, not an importable enrollment package.
                report["package"] = {"schema": package["schema"], "network": package["network"],
                                     "integrity": package["integrity"], "keyCustodyProved": True}
                policy_check = run(str(TOOL_BIN / "roko-validator-enroll"), "--rpc",
                                   f"http://127.0.0.1:{rpc_port}", "--check-rpc-policy")
                report["afterPolicy"] = json.loads(policy_check.stdout)
                report["policyBytesRestored"] = run("sudo", "-n", "cat", str(policy)).stdout == initial.read_text()
                if not report["policyBytesRestored"]:
                    raise ValueError("policy bytes not restored")
                baseline_keys = {p.name: p.read_bytes() for p in (root / "candidate").rglob("keystore/*") if p.is_file()}
                reuse_output = root / "reused-package.json"
                reuse_args = ["sudo", "-n", str(TOOL_BIN / "roko-session-key-window"),
                              "--service", unit, "--policy-file", str(policy),
                              "--rpc", f"http://127.0.0.1:{rpc_port}",
                               "--reuse-session-keys", package["session"]["encodedKeys"],
                              "--confirm-isolated-window", "--confirm-no-forwarding", "--",
                              "--binary", str(binary), "--expected-genesis", genesis,
                              "--minimum-peers", "2", "--observation-seconds", "8",
                              "--public-address", f"/ip4/127.0.0.1/tcp/{p2p_port}/p2p/{peer}",
                              "--output", str(reuse_output)]
                reused_result = run(*reuse_args, timeout=180)
                reused = json.loads(run("sudo", "-n", "cat", str(reuse_output)).stdout)
                keys_after = {p.name: p.read_bytes() for p in (root / "candidate").rglob("keystore/*") if p.is_file()}
                safe = run(str(TOOL_BIN / "roko-validator-enroll"), "--rpc",
                           f"http://127.0.0.1:{rpc_port}", "--check-rpc-policy")
                report["reuse"] = {
                    "helperExit": reused_result.returncode,
                    "sameTuple": reused["session"]["encodedKeys"] == package["session"]["encodedKeys"],
                    "freshPackage": reused["enrollmentId"] != package["enrollmentId"],
                    "existingKeyFilesPreserved": keys_after == baseline_keys,
                    "existingKeyCount": len(baseline_keys),
                    "safeAfter": json.loads(safe.stdout)["safeForNormalOperation"],
                    "policyBytesRestored": run("sudo", "-n", "cat", str(policy)).stdout == initial.read_text(),
                }
                del baseline_keys, keys_after
                if not all(report["reuse"][k] for k in ("sameTuple", "freshPackage", "existingKeyFilesPreserved", "safeAfter", "policyBytesRestored")):
                    raise ValueError("reuse failed")
                if agora_module:
                    # Independent local RPC observations bind importer expectations;
                    # do not derive expected network identity from the package itself.
                    observed_runtime = rpc(rpc_port, "state_getRuntimeVersion")
                    observed_metadata = rpc(rpc_port, "state_getMetadata")
                    expected_network = {
                        "chainName": rpc(rpc_port, "system_chain"),
                        "genesisHash": rpc(rpc_port, "chain_getBlockHash", [0]),
                        "specName": observed_runtime["specName"],
                        "specVersion": observed_runtime["specVersion"],
                        "transactionVersion": observed_runtime["transactionVersion"],
                        "metadataHash": "0x" + hashlib.sha256(bytes.fromhex(observed_metadata[2:])).hexdigest(),
                    }
                    report["agoraImport"] = {}
                    for label, candidate in (("generated", package), ("reused", reused)):
                        result = run("node", str(ROOT / "test/agora_enrollment_contract.mjs"),
                                     str(agora_module), agora_sha256,
                                     input=json.dumps({"package": candidate, "expected": expected_network}))
                        report["agoraImport"][label] = json.loads(result.stdout)
                report["faultCases"] = []
                for fault in ("unsafe-restart-failure", "term-interruption", "rpc-failure"):
                    # A successful window has already proved real generation.
                    # All faults are injected before the next rotation call.
                    baseline_keys = {p.name: p.read_bytes() for p in (root / "candidate").rglob("keystore/*") if p.is_file()}
                    fault_output = root / (fault + ".json")
                    if fault == "unsafe-restart-failure":
                        fail_start.touch()
                    helper_args = ["sudo", "-n", str(TOOL_BIN / "roko-session-key-window"),
                                   "--service", unit, "--policy-file", str(policy),
                                   "--rpc", f"http://127.0.0.1:{rpc_port}",
                                         "--confirm-isolated-window", "--confirm-no-forwarding", "--",
                                   "--binary", str(binary), "--expected-genesis", genesis,
                                   "--minimum-peers", "2", "--observation-seconds", "20",
                                   "--output", str(fault_output)]
                    helper = subprocess.Popen(helper_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, start_new_session=True)
                    injected = fault == "unsafe-restart-failure"
                    try:
                        if not injected:
                            deadline = time.monotonic() + 60
                            while time.monotonic() < deadline and helper.poll() is None:
                                try:
                                    accessible = rpc(rpc_port, "author_hasKey", ["0x" + "00" * 32, "babe"])
                                    if isinstance(accessible, bool):
                                        if fault == "term-interruption":
                                            run("sudo", "-n", "kill", "-TERM", "--", "-" + str(helper.pid))
                                        else:
                                            run("sudo", "-n", "systemctl", "stop", unit)
                                        injected = True
                                        break
                                except (OSError, ValueError):
                                    pass
                                time.sleep(0.2)
                        stdout, stderr = helper.communicate(timeout=120)
                    finally:
                        if helper.poll() is None:
                            run("sudo", "-n", "kill", "-TERM", "--", "-" + str(helper.pid))
                            helper.wait(timeout=30)
                        fail_start.unlink(missing_ok=True)
                    if not injected or helper.returncode == 0:
                        raise ValueError(f"fault not proven: {fault}")
                    restored = run(str(TOOL_BIN / "roko-validator-enroll"), "--rpc",
                                   f"http://127.0.0.1:{rpc_port}", "--check-rpc-policy")
                    keys_after = {p.name: p.read_bytes() for p in (root / "candidate").rglob("keystore/*") if p.is_file()}
                    case = {"fault": fault, "helperExit": helper.returncode,
                            "safeAfter": json.loads(restored.stdout)["safeForNormalOperation"],
                            "policyBytesRestored": run("sudo", "-n", "cat", str(policy)).stdout == initial.read_text(),
                            "noPackageWritten": not fault_output.exists(),
                            "existingKeyFilesPreserved": keys_after == baseline_keys,
                            "existingKeyCount": len(baseline_keys)}
                    report["faultCases"].append(case)
                    # No private bytes or secret-derived hashes enter the receipt.
                    del baseline_keys, keys_after
                    if not all(case[k] for k in ("safeAfter", "policyBytesRestored", "noPackageWritten", "existingKeyFilesPreserved")):
                        raise ValueError(f"fault recovery failed: {fault}")
                report["status"] = "pass"
            finally:
                cleanup_errors = []
                if installed:
                    for cleanup in (("systemctl", "stop", unit),
                                    ("rm", "--", str(unit_path)),
                                    ("systemctl", "daemon-reload")):
                        try:
                            run("sudo", "-n", *cleanup)
                        except Exception as error:
                            cleanup_errors.append(str(error))
                    installed = False
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                for log in logs:
                    log.close()
                report["processesStopped"] = all(p.poll() is not None for p in processes)
                report["serviceRemoved"] = not unit_path.exists()
                report["serviceStopped"] = subprocess.run(
                    ["systemctl", "is-active", "--quiet", unit]).returncode != 0
                if cleanup_errors or not report["serviceStopped"]:
                    report["cleanupErrors"] = cleanup_errors
                    raise RuntimeError("owned-resource cleanup was not fully verified")
        report["temporaryStateRemoved"] = True
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            # CLI diagnostics carry only public facts; exclude service logs/key files.
            report["commandStderr"] = error.stderr[-2000:] if error.stderr else ""
        raise
    finally:
        if "directory" in locals():
            report["temporaryStateRemoved"] = not Path(directory).exists()
        receipt.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--runtime-wasm", type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-runtime-spec", type=int, required=True)
    parser.add_argument("--tool-bin", type=Path, help="Installed command-link directory; defaults to source bin")
    parser.add_argument("--agora-module", type=Path)
    parser.add_argument("--agora-sha256")
    args = parser.parse_args()
    if args.tool_bin:
        TOOL_BIN = args.tool_bin.absolute()
    def interrupted(*_):
        raise KeyboardInterrupt("qualification interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    qualify(args.binary.resolve(), args.expected_sha256, args.receipt.resolve(),
            args.runtime_wasm.resolve(), args.expected_runtime_sha256, args.expected_runtime_spec,
            args.agora_module.resolve() if args.agora_module else None, args.agora_sha256)
