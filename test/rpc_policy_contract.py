#!/usr/bin/env python3
"""Real CLI/helper contract over loopback HTTP; service and generation are fixtures."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
DENIAL = {"code": 1040, "message": "RPC call is unsafe to be called externally"}


class PolicyContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.policy = self.path / "node-rpc.env"
        self.original = b"ROKO_RPC_METHODS=Safe\n"
        self.policy.write_bytes(self.original)
        self.policy.chmod(0o600)
        self.events = self.path / "events"
        self.events.touch()
        self.calls = []
        self.unsafe_result = {"result": False}
        self.safe_error = DENIAL
        self.break_restored_rpc = False
        case = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                method = request["method"]
                case.calls.append((method, request["params"]))
                if case.break_restored_rpc and "generated" in case.events.read_text() and case.policy.read_bytes() == case.original:
                    self.send_error(503)
                    return
                if method == "system_health":
                    result = {"result": {"isSyncing": False, "peers": 2}}
                elif method == "author_hasKey":
                    if request["params"] != ["0x" + "00" * 32, "babe"]:
                        result = {"error": {"code": -32602, "message": "Invalid params"}}
                    elif case.policy.read_bytes() == case.original:
                        result = {"error": case.safe_error}
                    else:
                        result = case.unsafe_result
                elif method == "author_hasSessionKeys":
                    # Exact historical failure. The new policy probe must not use it.
                    result = {"error": {"code": 1040, "message": "Session keys are not encoded correctly"}}
                else:
                    result = {"error": {"code": -32601, "message": "Method not found"}}
                payload = json.dumps({"jsonrpc": "2.0", "id": request["id"], **result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.env = dict(os.environ, POLICY=str(self.policy), EVENTS=str(self.events), ROOT=str(ROOT))
        self.env["ROKO_KEY_WINDOW_WAIT_ATTEMPTS"] = "1"
        self.env["PATH"] = str(self.path) + os.pathsep + self.env["PATH"]
        self.executable("id", '#!/bin/sh\nprintf "0\\n"\n')
        self.executable("stat", '''#!/bin/sh
if [ "$1" = -c ] && [ "$2" = %u ]; then printf '0\\n'; else exec /usr/bin/stat "$@"; fi
''')
        self.executable("systemctl", '''#!/bin/bash
set -eu
case "$1" in
cat) printf 'Environment=ROKO_RPC_METHODS=Safe\\nEnvironmentFile=-%s\\nExecStart=/node --rpc-methods ${ROKO_RPC_METHODS}\\n' "$POLICY" ;;
is-active) exit 0 ;;
restart)
  printf 'restart\\n' >>"$EVENTS"
  if [[ ${FAIL_UNSAFE_RESTART:-0} == 1 ]] && grep -qx 'ROKO_RPC_METHODS=Unsafe' "$POLICY"; then exit 1; fi
  ;;
stop) printf 'stop\\n' >>"$EVENTS" ;;
*) exit 1 ;;
esac
''')
        self.wrapper = self.executable("enroll", '''#!/bin/bash
set -eu
for arg in "$@"; do
  if [[ $arg == --check-rpc-policy ]]; then exec "$ROOT/bin/roko-validator-enroll" "$@"; fi
done
grep -qx 'ROKO_RPC_METHODS=Unsafe' "$POLICY"
printf '%s\\n' "$@" >"$EVENTS.args"
printf 'generated\\n' >>"$EVENTS"
if [[ ${INTERRUPT:-0} == 1 ]]; then kill -TERM "$PPID"; exit 143; fi
exit "${GENERATION_RC:-0}"
''')

    def executable(self, name, text):
        path = self.path / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def check(self):
        return subprocess.run([str(ROOT / "bin/roko-validator-enroll"), "--rpc", self.url,
                               "--check-rpc-policy"], capture_output=True, text=True, timeout=10)

    def window(self, helper_args=(), **environment):
        return subprocess.run([
            str(ROOT / "bin/roko-session-key-window"), "--rpc", self.url,
            "--policy-file", str(self.policy), "--enroll-command", str(self.wrapper),
            "--confirm-isolated-window", "--confirm-no-forwarding", *helper_args, "--",
            "--output", str(self.path / "package.json"),
        ], env=self.env | environment, capture_output=True, text=True, timeout=15)

    def assert_restored(self):
        self.assertEqual(self.policy.read_bytes(), self.original)
        backups = list(self.path.glob("node-rpc.env.before-session-key-window-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o600)
        self.assertTrue(all(method in {"system_health", "author_hasKey"} for method, _ in self.calls))

    def test_cli_exit_contract(self):
        for code in (1040, -32601):
            self.safe_error = DENIAL | {"code": code}
            result = self.check()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["safeForNormalOperation"])
        self.policy.write_text("ROKO_RPC_METHODS=Unsafe\n")
        for value in (True, False):
            self.unsafe_result = {"result": value}
            result = self.check()
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(json.loads(result.stdout)["safeForNormalOperation"])
        for response in (
            {"error": {"code": 1040, "message": "Session keys are not encoded correctly"}},
            {"error": {"code": -32602, "message": "Invalid params"}},
            {"error": {"code": -32601, "message": "Access denied by proxy"}},
            {"error": {"code": -32601, "message": "Method not found"}},
            {"result": "false"}, {"result": None}, {"result": 0},
        ):
            with self.subTest(response=response):
                self.unsafe_result = response
                self.assertEqual(self.check().returncode, 1)

    def test_guarded_success_with_real_cli(self):
        result = self.window()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "generated", "restart"])
        self.assert_restored()

    def test_reuse_mode_never_requests_generation(self):
        public_tuple = "0x" + "ab" * 224
        result = self.window(helper_args=("--reuse-session-keys", public_tuple))
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = Path(str(self.events) + ".args").read_text().splitlines()
        self.assertIn("--session-keys", arguments)
        self.assertIn(public_tuple, arguments)
        self.assertNotIn("--confirm-new-keys", arguments)
        self.assertNotIn("--confirm-isolated-unsafe-rpc", arguments)
        self.assert_restored()

    def test_invalid_reuse_tuple_never_restarts(self):
        result = self.window(helper_args=("--reuse-session-keys", "0x"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events.read_text(), "")
        self.assertEqual(self.policy.read_bytes(), self.original)
        self.assertFalse(list(self.path.glob("*.before-session-key-window-*")))

    def test_reuse_failure_restores_without_generation_fallback(self):
        result = self.window(helper_args=("--reuse-session-keys", "0x" + "ab" * 224), GENERATION_RC="7")
        self.assertEqual(result.returncode, 7)
        arguments = Path(str(self.events) + ".args").read_text().splitlines()
        self.assertNotIn("--confirm-new-keys", arguments)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "generated", "restart"])
        self.assert_restored()

    def test_installer_symlink_uses_cli_from_same_version(self):
        installed = self.path / "installed" / "1.4.1" / "bin"
        installed.mkdir(parents=True)
        helper = installed / "roko-session-key-window"
        helper.write_bytes((ROOT / "bin/roko-session-key-window").read_bytes())
        helper.chmod(0o755)
        cli = installed / "roko-validator-enroll"
        cli.write_bytes(self.wrapper.read_bytes())
        cli.chmod(0o755)
        links = self.path / "links"
        links.mkdir()
        (links / helper.name).symlink_to(helper)
        (links / cli.name).symlink_to(cli)
        result = subprocess.run([
            str(links / helper.name), "--rpc", self.url,
            "--policy-file", str(self.policy),
            "--confirm-isolated-window", "--confirm-no-forwarding", "--",
            "--output", str(self.path / "package.json"),
        ], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "generated", "restart"])
        self.assert_restored()

    def test_exact_prior_policy_bytes_are_restored(self):
        self.original = b"ROKO_RPC_METHODS=Safe\r\n"
        self.policy.write_bytes(self.original)
        result = self.window()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_restored()

    def test_unknown_rpc_never_reaches_generation(self):
        self.unsafe_result = {"error": {"code": -32000, "message": "keystore unavailable"}}
        self.assertEqual(self.window().returncode, 1)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "restart"])
        self.assert_restored()

    def test_restart_failure_restores(self):
        self.assertEqual(self.window(FAIL_UNSAFE_RESTART="1").returncode, 1)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "restart"])
        self.assert_restored()

    def test_generation_failure_restores(self):
        self.assertEqual(self.window(GENERATION_RC="7").returncode, 7)
        self.assert_restored()

    def test_interruption_restores(self):
        self.assertEqual(self.window(INTERRUPT="1").returncode, 143)
        self.assert_restored()

    def test_failed_restoration_proof_stops_service(self):
        self.break_restored_rpc = True
        result = self.window()
        self.assertEqual(result.returncode, 1)
        self.assertIn("CRITICAL", result.stderr)
        self.assertEqual(self.events.read_text().splitlines(), ["restart", "generated", "restart", "stop"])
        self.assert_restored()


if __name__ == "__main__":
    unittest.main()
