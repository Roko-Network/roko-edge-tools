"""Read-only wallet setup handoff: public chain facts for a browser wallet; never signs."""
import json
from pathlib import Path
from typing import Any, Callable

from validator_contract import TOOL_VERSION, TESTNET_GENESIS, HASH, ACCOUNT, EnrollmentError

def wallet_setup(rpc: "RpcClient", account: str) -> dict[str, Any]:
    """Read public chain facts for a wallet-owned browser handoff; never sign."""
    if not ACCOUNT.fullmatch(account):
        raise EnrollmentError("Wallet setup requires only a public 20-byte 0x account address")
    if rpc.call("chain_getBlockHash", [0]) != TESTNET_GENESIS:
        raise EnrollmentError("Wallet setup RPC is not the configured ROKO testnet")
    if rpc.call("eth_chainId") != "0xcc92":
        raise EnrollmentError("Wallet setup EVM chain ID does not match 52370")
    finalized = rpc.call("chain_getFinalizedHead")
    if not isinstance(finalized, str) or not HASH.fullmatch(finalized):
        raise EnrollmentError("Wallet setup requires a valid finalized block hash")
    runtime = rpc.call("state_getRuntimeVersion", [finalized])
    if not isinstance(runtime, dict) or any(
        type(runtime.get(key)) is not int or runtime[key] < 0
        for key in ("specVersion", "transactionVersion")
    ):
        raise EnrollmentError("Wallet setup runtime response is malformed")
    return {
        "schema": "roko.wallet-setup.v1",
        "toolVersion": TOOL_VERSION,
        "account": account,
        "network": {"name": "ROKO Testnet", "chainType": "substrate",
                    "rpcWss": "wss://rpc.roko.network", "chainId": 52370,
                    "genesisHash": TESTNET_GENESIS, "finalizedHash": finalized,
                    "specVersion": runtime["specVersion"],
                    "transactionVersion": runtime["transactionVersion"]},
        "signingInterface": "substrate-signPayload",
        "accountType": "ethereum-account-id20",
        "walletConnectionVerified": False,
        "metadataVerified": False,
        "packageAcceptanceVerified": False,
        "readyToSign": False,
        "links": {"agora": "https://agora.roko.network/participate/staking/",
                  "guide": "https://docs.roko.network/pages/wallets-faucet.html",
                  "talisman": "https://www.talisman.xyz/download",
                  "toolCatalog": "https://downloads.roko.network/validator-tools/current/"},
        "nextActions": [
            "Use a desktop browser with a Substrate-signing extension. Ordinary MetaMask/EVM mode cannot sign Agora staking/session calls.",
            "Talisman is the documented path with reported enrollment success; verify support for your intended account and network.",
            "If moving an account between wallets, perform any import only inside the official wallet UI. Never give this tool or an agent a private key or recovery phrase.",
            f"Verify the wallet and Agora both display the exact intended account {account}; a watch-only account cannot sign.",
            "Add ROKO as a custom Substrate network using the public WSS above. Verify genesis and current metadata in Agora; these observed RPC facts alone do not prove wallet compatibility.",
            "Only after the wallet network is verified, prepare a release-compatible enrollment package on the non-authoring node. Confirm Safe RPC restoration and Package verified in Agora before wallet actions.",
            "Compare installed tool identity with the signed catalog and actual Agora importer contract. Version labels alone do not prove package acceptance.",
            "If the package expires, use the supported refresh/reissue path without editing expiry or tuple. Expiry alone does not require new keys.",
            "Review each exact transaction and fee in the wallet; retain finalized transaction hashes. This handoff neither signs nor proves enrollment.",
        ],
    }



def run_wallet_setup(args: Any, rpc_factory: Callable[[str], Any], loopback_rpc: Callable[[str], Any]) -> int:
    """CLI entry for --wallet-setup; refuses to mix with enrollment or key operations."""
    if args.check_account or args.expected_session_keys or args.check_rpc_policy or args.save_readiness or args.confirm_new_keys or args.session_keys or args.confirm_isolated_unsafe_rpc or args.public_address:
        raise EnrollmentError("Wallet setup cannot be combined with enrollment, key generation, readiness or key RPC operations")
    loopback_rpc(args.rpc)
    handoff = wallet_setup(rpc_factory(args.rpc), args.wallet_setup)
    if args.output:
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise EnrollmentError("Wallet setup output must be a new file; do not overwrite an enrollment package")
        # Exclusive creation avoids clobbering a package if another process races us.
        with output.open("x", encoding="utf-8") as handle:
            json.dump(handoff, handle, indent=2)
            handle.write("\n")
    print(json.dumps(handoff, indent=2))
    return 0
