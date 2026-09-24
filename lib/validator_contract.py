"""Shared public-only validator contract primitives."""
import re
from typing import Any

SCHEMA = "roko.validator-enrollment.v1"
TOOL_VERSION = "1.4.1"
TESTNET_GENESIS = "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"
KEY_TYPES = ["grandpa", "babe", "imOnline", "authorityDiscovery", "mixnet", "beefy", "temporal"]
READINESS_STATES = {
    "NON_AUTHORING_NODE", "SYNCING", "SESSION_KEYS_UNRESOLVED",
    "SESSION_KEYS_MISMATCH", "SESSION_KEYS_REGISTERED", "CANDIDATE", "QUEUED",
    "ACTIVE_BABE_KEY_MISMATCH", "ACTIVE_TEMPORAL_KEY_MISMATCH",
    "ACTIVE_INITIALIZING", "CONVERGED", "AUTHORED",
}
PROHIBITED_KEY = re.compile(r"(?:secret|private|seed|mnemonic|phrase|suri|keystore|vault|openbao|token|password|cookie|approle|nodekey)", re.I)
HASH = re.compile(r"^0x[0-9a-f]{64}$", re.I)
ENCODED_KEYS = re.compile(r"^0x(?:[0-9a-f]{2}){32,1024}$", re.I)
ACCOUNT = re.compile(r"^0x[0-9a-f]{40}$", re.I)
MASK64 = (1 << 64) - 1


class EnrollmentError(RuntimeError):
    """Expected operator-facing enrollment failure."""

class RpcRejectedError(EnrollmentError):
    """A structurally valid JSON-RPC rejection, kept distinct from transport errors."""

    def __init__(self, method: str, code: int | None, message: str) -> None:
        self.method = method
        self.code = code
        self.rpc_message = message
        rendered_code = f" (code {code})" if code is not None else ""
        super().__init__(f"Local node RPC rejected {method}{rendered_code}: {message}")

def scan_prohibited(value: Any, path: str = "$") -> None:
    if isinstance(value, list):
        for index, entry in enumerate(value):
            scan_prohibited(entry, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, entry in value.items():
            if PROHIBITED_KEY.search(key) and key != "hasSessionKeys":
                raise EnrollmentError(f'{path} contains prohibited field "{key}"')
            scan_prohibited(entry, f"{path}.{key}")


