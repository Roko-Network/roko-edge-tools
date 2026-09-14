# Existing-install enrollment preflight

Complete these checks before restarting a custom installation or opening a
key window. Package generation, package acceptance, wallet transactions and
active membership are separate milestones.

1. **Identify the chain and artifacts.** Query the local RPC genesis and runtime;
   testnet genesis must be
   `0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb`,
   chain ID 52370. Record the signed node release ID, full source revision,
   executable digest and (for Docker) immutable image ID/source label. Compare
   against authenticated release metadata. Record the separate tool version.
   A display suffix or matching release number is insufficient.
2. **Prove required capabilities.** Inspect `rpc_methods` for
   `temporal_getValidatorReadiness`, key-custody methods and normal chain/health
   methods. Require advancing finalized heads, a synchronized clock, a synced
   node and the intended peers. Enrollment package peer-count checks do not
   prove temporal quorum; check mapped active sources and readiness separately.
3. **Preserve the custom service contract.** Retain protected rollback copies
   of the effective systemd unit/drop-ins, RPC policy and Docker invocation.
   Record device mappings, PHC device/provider flags, numeric device access,
   user/group, base path, chain-spec identity, peer identity, socket mounts and
   readiness checks locally. Do not put credentials or private configuration
   contents into a support report. Compare the proposed service with those
   originals before restart. The generic Chrony installer is not a replacement
   for a PHC derivative; retain its PHC settings and health gate explicitly.
4. **Make the node non-authoring deliberately.** Verify the local RPC reports
   Full rather than Authority before packaging, including reuse. Preserve the
   validator configuration for a later controlled transition. Do not switch a
   running elected authority to Full as an incidental installer action.
5. **Prove the RPC boundary.** Run `roko-validator-enroll --check-rpc-policy`
   against loopback and require exit 0. Inspect listeners and all forwarding
   paths, including Docker port publishing, reverse proxies and tunnels. A
   loopback bind alone does not rule out forwarding. The helper requires its
   supported policy-variable unit contract; a hardcoded Safe custom unit needs
   a reviewed adaptation that preserves the settings recorded in step 3.
6. **Choose reuse or rotation.** For an existing tuple, verify its public
   identity and local custody; refresh the package without generating keys.
   Signed tooling 1.4.0 exposes CLI reuse but its helper supports generation
   only. Tooling 1.4.1 adds the guarded reuse option; verify the installed
   version before choosing it. Rotation is a separate
   intentional action. Retain old key custody until the replacement is proven
   active, and never edit a package's expiry or tuple to bypass validation.
7. **Prepare the intended wallet before the short package window.** Agora's
   browser path requires its supported Substrate extrinsic signer for the
   intended AccountId20 account. An EIP-1193 MetaMask connection alone does not
   establish that capability. Check account/network and signer access first;
   keep wallet secrets with the owner. A node-wallet alternative has its own
   explicit operator signing steps and is not evidence of browser acceptance.
8. **Verify after the window.** Require exact prior policy restoration, Safe
   RPC exit 0, preserved device/clock/readiness behavior and unchanged keys for
   reuse. Retain recovery backups. If Safe recovery cannot be proved, the
   helper stops the service; repair and verify it before import or candidacy.
9. **Verify the handoff separately.** Import the unedited fresh package into
   Agora. Its integrity, expiry, genesis, metadata, proof mode and local public
   tuple must pass the actual importer. The owner reviews and signs each
   required transaction. Record finalized successful dispatch, matching
   next-session keys and candidate intent; verify election, active membership
   and finalized authorship separately. Neither an import nor a finalized
   `validate` call proves an active validator.

The exact native enrollment qualifications for tooling 1.4.0 are in
[guarded enrollment qualification](guarded-enrollment-qualification.md).
They do not certify a custom PHC derivative, Docker timing behavior, the
owner's wallet integration or an external host's transport reachability.
