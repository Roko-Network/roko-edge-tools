#!/usr/bin/env python3
"""Private, read-only enrollment assessment from authenticated release artifacts.

Candidate mode records out-of-support evidence; it never creates a delivery
binding or changes signed compatibility. No service, RPC or publication action.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

FINGERPRINT = "62297562B1C7053088F405DB0117DAAA677A5BF2"
LIVE_GENESIS = "0x0a2296f8f036f71437e8f6f2028ccbf0dc3dd6b3de9120fc15e43789c794e8bb"
LEGACY = {"version": "1.4.5", "source": "864d66340f3cef1d2bf1b1c3e45b8f87b5c27bfa",
          "archive": "b1c371618a91369bd1e4537485dbce165d9d58cd5bb1e1b2b38bcca45e29b162",
          "metadata": "e0f27be38a992857af91b8c3a5ef368f2ea88cf716353907843d8a53ee7b8c31",
          "checksums": "2383bb810f1ff6ac50c2284fd94dacb65c755fd85e46e8fec689cbb0b95a53a3",
          "compatibility": "e95124c4378861d41d82b457357557f6c5eb1a5cd7e995eba70fc803d8cefabd",
          "installer": "2469448320d8710581b676f6c784b7182907329fa8351dcb9ccf5a75cc556aff",
          "publicKey": "4cc7695aabf0307f1a465584d4cde33cdfa88ca30add3001cd5ca6805a2dd2b9"}
NEGATIVE = {"wrongGenesis", "wrongRuntime", "wrongMetadata", "expired", "tampered", "replayed"}
FAULTS = {"unsafe-restart-failure", "term-interruption", "rpc-failure"}
COMMANDS = ("roko-validator-enroll", "roko-session-key-window", "roko-authority-peers", "roko-validator-watch")

class VerificationError(ValueError):
    pass

def require(value, message):
    if not value:
        raise VerificationError(message)

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text())

def verify_signature(path, signature, public_key):
    """Public-only disposable keyring; exact primary/signing fingerprint."""
    with tempfile.TemporaryDirectory(prefix='enrollment-public-gpg-', dir='/dev/shm') as home:
        os.chmod(home, 0o700)
        base = ['gpg', '--batch', '--homedir', home]
        shown = subprocess.run(base + ['--with-colons', '--import-options', 'show-only', '--import', str(public_key)],
                               check=True, capture_output=True, text=True, timeout=15)
        fingerprints = [line.split(':')[9] for line in shown.stdout.splitlines() if line.startswith('fpr:')]
        require(fingerprints and fingerprints[0] == FINGERPRINT, 'Unapproved signing key')
        subprocess.run(base + ['--import', str(public_key)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        result = subprocess.run(base + ['--status-fd', '1', '--verify', str(signature), str(path)],
                                capture_output=True, text=True, timeout=15)
        valid = [line.split() for line in result.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
        require(result.returncode == 0 and len(valid) == 1 and
                (valid[0][2] == FINGERPRINT or valid[0][-1] == FINGERPRINT), 'Detached signature did not authenticate approved authority')

def checksums(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) [ *]([^\s]+)', line)
        require(match is not None, 'Malformed signed checksum row')
        value, name = match.groups()
        require(PurePosixPath(name).name == name and name not in ('.', '..') and name not in result,
                'Checksum paths must be unique basenames')
        result[name] = value
    require(result, 'Empty signed checksums')
    return result

def closed_installed_files(package_root, files):
    """No unsigned importable files, bytecode, links or special files."""
    observed = set()
    def unreadable(_):
        raise VerificationError('Cannot enumerate installed package')
    for current, directories, names in os.walk(package_root, followlinks=False, onerror=unreadable):
        for name in directories:
            require(name != '__pycache__', 'Unsigned installed bytecode cache')
            require(not (Path(current) / name).is_symlink(), 'Unsigned installed directory link')
        for name in names:
            path = Path(current) / name
            require(path.is_file() and not path.is_symlink(), 'Unsigned installed link/special file')
            observed.add(path.relative_to(package_root).as_posix())
    require(observed == set(files), 'Installed package file set differs from signed archive')

def authenticated_tools(directory, tool_bin):
    directory, tool_bin = Path(directory), Path(tool_bin)
    key = directory / 'roko-release-signing-key.asc'
    verify_signature(directory / 'SHA256SUMS', directory / 'SHA256SUMS.asc', key)
    table = checksums(directory / 'SHA256SUMS')
    for asset in ('install-roko-validator-enroll.sh', 'roko-release-signing-key.asc'):
        require(digest(directory / asset) == table.get(asset), 'Signed installer/public-key checksum mismatch')
    names = [name for name in table if re.fullmatch(r'roko-validator-enroll-[0-9]+\.[0-9]+\.[0-9]+\.metadata\.json', name)]
    require(len(names) == 1, 'Signed manifest must identify exactly one tools metadata file')
    metadata_path = directory / names[0]
    verify_signature(metadata_path, Path(str(metadata_path) + '.asc'), key)
    require(digest(metadata_path) == table[names[0]], 'Tools metadata checksum mismatch')
    metadata = read_json(metadata_path)
    require(metadata.get('schema') == 'roko.validator-enroll-release.v1', 'Wrong tools release schema')
    version = metadata.get('tool', {}).get('version', '')
    source = metadata.get('source', {}).get('revision', '')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) and re.fullmatch(r'[0-9a-f]{40}', source), 'Malformed authenticated tool identity')
    require(metadata.get('source', {}).get('repository') == 'https://github.com/Roko-Network/roko-edge-tools', 'Wrong authenticated tool repository')
    archive_name = f'roko-validator-enroll-{version}.tar.gz'
    archive = directory / archive_name
    require(metadata.get('artifact', {}).get('file') == archive_name and
            digest(archive) == metadata['artifact']['sha256'] == table.get(archive_name), 'Tools archive checksum mismatch')
    require(archive.stat().st_size == metadata['artifact']['bytes'], 'Tools archive size mismatch')
    roots, installed = set(), {}
    for name in COMMANDS:
        link = tool_bin / name
        require(link.is_symlink(), 'Every installed command must be an actual installer link')
        resolved = link.resolve(strict=True)
        require(resolved.name == name and resolved.parent.name == 'bin', 'Installed link target has wrong command shape')
        roots.add(resolved.parent.parent)
        installed[name] = resolved
    require(len(roots) == 1, 'Installed commands resolve into different packages')
    package_root = roots.pop()
    require(package_root.name == version, 'Installed links do not resolve into the authenticated version directory')
    prefix = f'roko-validator-enroll-{version}/'
    files = {}
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle.getmembers():
            if member.isdir():
                continue
            require(member.isfile() and member.name.startswith(prefix), 'Tools archive contains link/device/out-of-package member')
            relative = PurePosixPath(member.name[len(prefix):])
            require(relative.parts and not relative.is_absolute() and '..' not in relative.parts and str(relative) not in files,
                    'Unsafe or duplicate archive member')
            require(member.size <= 4 * 1024 * 1024, 'Tool member exceeds reviewed size bound')
            raw = bundle.extractfile(member).read()
            actual = package_root.joinpath(*relative.parts)
            require(actual.is_file() and not actual.is_symlink() and actual.resolve().is_relative_to(package_root), 'Installed member escapes signed package')
            expected = hashlib.sha256(raw).hexdigest()
            require(digest(actual) == expected, 'Installed package differs from signed archive: ' + str(relative))
            files[str(relative)] = expected
    require({f'bin/{name}' for name in COMMANDS}.issubset(files),
            'Signed archive must contain all four installed commands')
    closed_installed_files(package_root, files)
    compatibility_path = package_root / 'compatibility/validator-enroll-compatibility.json'
    require(digest(compatibility_path) == metadata['compatibility']['sha256'], 'Compatibility digest mismatch')
    compatibility = read_json(compatibility_path)
    require(compatibility.get('schema') == 'roko.validator-enroll-compatibility.v1' and
            compatibility.get('tool', {}).get('version') == version and
            compatibility.get('tool', {}).get('sourceRevision') == source, 'Authenticated compatibility/tool identity mismatch')
    require(compatibility.get('network', {}).get('genesisHash') == LIVE_GENESIS and
            compatibility.get('network', {}).get('chainId') == '52370', 'Wrong published compatibility network')
    actual_version = subprocess.run([str(installed['roko-validator-enroll']), '--version'], check=True,
                                    capture_output=True, text=True, timeout=15,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')).stdout.strip()
    closed_installed_files(package_root, files)
    require(actual_version == f'roko-validator-enroll {version}', 'Installed command version differs from authenticated package')
    if version == LEGACY['version']:
        require(source == LEGACY['source'] and digest(archive) == LEGACY['archive'], 'Immutable legacy release was replaced')
        require(digest(metadata_path) == LEGACY['metadata'] and digest(directory / 'SHA256SUMS') == LEGACY['checksums'] and
                digest(compatibility_path) == LEGACY['compatibility'] and digest(key) == LEGACY['publicKey'] and
                digest(directory / 'install-roko-validator-enroll.sh') == LEGACY['installer'], 'Immutable legacy artifact hashes changed')
        require(compatibility['runtime'] == {'minimumSpecVersion': 285, 'maximumSpecVersion': 287}, 'Legacy compatibility changed')
    return {'version': version, 'sourceRevision': source, 'compatibility': compatibility,
            'files': files, 'installed': {name: str(path) for name, path in installed.items()},
            'archiveSha256': digest(archive), 'metadataSha256': digest(metadata_path),
            'checksumsSha256': digest(directory / 'SHA256SUMS')}

def binary_architecture(path):
    with Path(path).open('rb') as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01', 'Native qualification requires little-endian ELF64')
    architecture = {62: 'amd64', 183: 'arm64'}.get(int.from_bytes(header[18:20], 'little'))
    require(architecture is not None, 'Unsupported native binary architecture')
    return architecture

def authenticated_node(args):
    verify_signature(args.node_metadata, args.node_metadata_signature, args.node_public_key)
    verify_signature(args.node_checksums, args.node_checksums_signature, args.node_public_key)
    table = checksums(args.node_checksums)
    require(table.get(args.node_metadata.name) == digest(args.node_metadata), 'Node metadata not covered by signed manifest')
    metadata = read_json(args.node_metadata)
    require(re.fullmatch(r'[0-9a-f]{40}', metadata.get('source_revision', '')), 'Missing full node source revision')
    image = metadata.get('images', {}).get(args.architecture, '')
    require(re.fullmatch(r'.+@sha256:[0-9a-f]{64}', image), 'Node image lacks immutable digest')
    require(binary_architecture(args.binary) == args.architecture, 'Native binary architecture mismatch')
    inputs = {'binary': args.binary, 'runtimeWasm': args.runtime_wasm, 'agoraModule': args.agora_module}
    values = {role: digest(path) for role, path in inputs.items()}
    if args.node_binding:
        require(args.node_binding_signature is not None, 'Private attestation signature required')
        verify_signature(args.node_binding, args.node_binding_signature, args.node_public_key)
        binding = read_json(args.node_binding)
        require(binding.get('schema') == 'roko.enrollment-artifact-attestation.v1' and
                binding.get('issuer') == 'roko-operator-private-qualification', 'Wrong private attestation issuer/schema')
        require(binding.get('sourceRevision') == metadata['source_revision'] and
                re.fullmatch(r'[0-9a-f]{40}', binding.get('sourceTree', '')) and
                binding.get('architecture') == args.architecture and binding.get('image') == image,
                'Private attestation/node identity mismatch')
        require(binding.get('releaseMetadataSha256') == digest(args.node_metadata) and
                binding.get('releaseChecksumsSha256') == digest(args.node_checksums), 'Private attestation release binding mismatch')
        require(set(binding.get('roles', {})) == set(inputs), 'Attestation roles incomplete')
        for role, path in inputs.items():
            row = binding['roles'][role]
            require(row.get('sha256') == values[role] and Path(row.get('path', '')).resolve() == path.resolve(), 'Private role path/hash mismatch: ' + role)
        require(binding['roles']['runtimeWasm'].get('derivation') == 'independently-reproduced-production' and
                binding['roles']['agoraModule'].get('derivation') == 'exact-source-export', 'Derived artifact roles lack explicit provenance')
        binary = binding['roles']['binary']
        require(binary.get('derivation') == 'signed-native-archive', 'Binary must derive from authenticated native archive')
        archive = args.node_archive
        require(archive is not None and table.get(archive.name) == digest(archive) == binary.get('archiveSha256'), 'Native archive signed checksum mismatch')
        member_name = binary.get('archiveMember')
        require(isinstance(member_name, str) and PurePosixPath(member_name).name == 'roko-node' and
                not PurePosixPath(member_name).is_absolute() and '..' not in PurePosixPath(member_name).parts, 'Invalid native binary member')
        with tarfile.open(archive, 'r:gz') as bundle:
            matching = [member for member in bundle.getmembers() if member.name == member_name]
            require(len(matching) == 1 and matching[0].isfile(), 'Native archive binary member missing/ambiguous')
            stream = bundle.extractfile(matching[0])
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == values['binary'], 'Exported native binary differs from signed archive')
        provenance = {'kind': 'signed-operator-derived-attestation', 'issuer': binding['issuer'], 'sha256': digest(args.node_binding)}
    else:
        require(args.node_binding_signature is None and args.node_archive is None, 'Derived binding inputs require explicit attestation')
        for role, path in inputs.items():
            require(table.get(path.name) == values[role], 'Exact role is not directly covered by authenticated checksum: ' + role)
        provenance = {'kind': 'direct-signed-checksum-coverage'}
    return metadata, image, values, provenance

def assess_receipt(receipt, args, tools, node, image, values, provenance):
    r = receipt
    require(r.get('status') == 'pass' and r.get('liveChainUsed') is False, 'Disposable gate did not pass')
    require(r.get('genesis') != LIVE_GENESIS and re.fullmatch(r'0x[0-9a-f]{64}', r.get('genesis', '')), 'Fixture genesis is invalid/live')
    require(r.get('binarySha256') == values['binary'] and r.get('runtimeCodeSha256') == values['runtimeWasm'], 'Node runtime/binary tuple mismatch')
    require(type(args.runtime_spec) is int and r.get('expectedRuntimeSpec') == args.runtime_spec and
            r.get('before', {}).get('runtime', {}).get('specVersion') == args.runtime_spec, 'Runtime spec mismatch')
    require(digest(args.harness) == args.expected_harness_sha256 == r.get('harnessSha256'), 'Revised harness reviewed pin mismatch')
    require(digest(args.wrapper) == args.expected_wrapper_sha256 == r.get('wrapperSha256'), 'Reviewed resource wrapper pin mismatch')
    require(r.get('toolVersion') == f"roko-validator-enroll {tools['version']}" and
            r.get('installedCommandLinks') is True and
            r.get('helperSha256') == tools['files']['bin/roko-session-key-window'], 'Authenticated installed helper identity mismatch')
    require(r.get('installedResolvedCommands') == tools['installed'], 'Recorded installed-link resolution mismatch')
    require(type(r.get('helperExit')) is int and r.get('helperExit') == 0 and r.get('policyBytesRestored') is True and
            r.get('afterPolicy', {}).get('safeForNormalOperation') is True, 'Generation/Safe restoration failed')
    custody = r.get('keyCustodyEvidence', {})
    require(custody.get('helperAttested') is True and custody.get('method') == 'author_hasSessionKeys' and
            custody.get('validatorEnrollmentSha256') == tools['files']['lib/validator_enrollment.py'], 'Explicit authenticated helper custody evidence missing')
    reuse = r.get('reuse', {})
    require(type(reuse.get('helperExit')) is int and reuse.get('helperExit') == 0 and type(reuse.get('existingKeyCount')) is int and reuse['existingKeyCount'] == 7, 'Seven-key reuse evidence missing')
    for name in ('sameTuple', 'freshPackage', 'existingKeyFilesPreserved', 'safeAfter', 'policyBytesRestored'):
        require(reuse.get(name) is True, 'Reuse evidence missing: ' + name)
    observation = reuse.get('custodyObservation', {})
    require(observation.get('method') == 'author_hasSessionKeys' and observation.get('additionalUnsafeWindowOpened') is False and
            ((observation.get('status') == 'independently-observed' and observation.get('observedTrue') is True) or
             (observation.get('status') == 'helper-attested-window-closed' and observation.get('observedTrue') is False)),
            'Reuse custody observation must accurately distinguish independent and helper attestation')
    for label in ('generated', 'reused'):
        imported = r.get('agoraImport', {}).get(label, {})
        require(imported.get('accepted') is True and imported.get('moduleSha256') == values['agoraModule'], 'Actual Agora module did not accept ' + label)
        rejected = imported.get('rejected', {})
        require(set(rejected) == NEGATIVE and all(rejected[name] is True for name in NEGATIVE), 'All six Agora negatives must explicitly pass')
        expected = imported.get('expected', {})
        package_network = r.get('package', {}).get('network', {})
        fields = {'chainName','genesisHash','specName','specVersion','transactionVersion','metadataHash'}
        require(set(package_network) == fields and set(expected) == fields, 'Unexpected/incomplete public network tuple')
        require(type(expected.get('transactionVersion')) is int and expected['transactionVersion'] > 0 and
                isinstance(expected.get('chainName'), str) and bool(expected['chainName']) and
                isinstance(expected.get('specName'), str) and bool(expected['specName']) and
                re.fullmatch(r'0x[0-9a-f]{64}', expected.get('metadataHash', '')), 'Agora expected tuple incomplete')
        require(expected.get('genesisHash') == r.get('genesis') and type(expected.get('specVersion')) is int and
                expected['specVersion'] == args.runtime_spec and
                all(type(expected[name]) is type(package_network[name]) and expected[name] == package_network[name] for name in fields),
                'Agora independent network tuple mismatch')
    faults = r.get('faultCases', [])
    require(len(faults) == 3 and {f.get('fault') for f in faults} == FAULTS, 'Three unique fault cases required')
    for fault in faults:
        require(type(fault.get('helperExit')) is int and fault['helperExit'] != 0 and
                type(fault.get('existingKeyCount')) is int and fault['existingKeyCount'] == 7, 'Fault did not fail/preserve seven keys')
        for name in ('safeAfter', 'policyBytesRestored', 'noPackageWritten', 'existingKeyFilesPreserved'):
            require(fault.get(name) is True, 'Fault recovery evidence missing: ' + name)
    for name in ('processesStopped', 'serviceStopped', 'serviceRemoved', 'temporaryStateRemoved'):
        require(r.get(name) is True, 'Cleanup evidence missing: ' + name)
    require(r.get('cleanupErrors', []) == [], 'Cleanup errors remain')
    resources = r.get('resources', {})
    require(resources.get('verified') is True and resources.get('sliceMemoryMax') == 12 * 1024**3 and
            resources.get('sliceCpuQuotaPerSecUSec') == 4_000_000 and resources.get('sliceTasksMax') == 1024 and
            resources.get('runtimeMaxUSec') == 1_800_000_000 and resources.get('timeoutStopUSec') == 90_000_000 and
            resources.get('candidateMemoryMax') == 2 * 1024**3, 'Owned finite cgroup contract not proved')
    require(r.get('campaignSliceStopped') is True and r.get('campaignSliceRemoved') is True and
            r.get('productionServiceIdentityPreserved') is True and r.get('wrapperCleanupErrors') == [], 'Campaign cleanup/production isolation not proved')
    compatibility = tools['compatibility']
    minimum, maximum = compatibility['runtime']['minimumSpecVersion'], compatibility['runtime']['maximumSpecVersion']
    if args.mode == 'candidate':
        require(tools['version'] == '1.4.5' and args.runtime_spec == 290 and not minimum <= args.runtime_spec <= maximum,
                'Candidate mode is only explicit290 outside immutable1.4.5 support')
        schema, outside = 'roko.enrollment-candidate-assessment.v1', True
    else:
        require(minimum <= args.runtime_spec <= maximum, 'Outside authenticated published compatibility')
        if tools['version'] != '1.4.5':
            require(minimum == maximum == args.runtime_spec, 'New release only qualifies the exact observed runtime')
        matches = [row for row in compatibility.get('node', {}).get('qualifiedBuilds', []) if
                   row.get('sourceRevision') == node['source_revision'] and row.get('binarySha256') == values['binary'] and
                   row.get('runtimeSpecVersion') == args.runtime_spec and row.get('platform') == 'linux-' + args.architecture and
                   row.get('displayVersion') in (r.get('binaryVersion'), r.get('binaryVersion', '').removeprefix('roko-node '))]
        require(len(matches) == 1, 'Node tuple lacks exact authenticated qualified-build entry')
        schema, outside = 'roko.enrollment-delivery-binding.v2', False
    return {'schema': schema, 'status': 'pass', 'outsidePublishedCompatibility': outside,
            'deliveryBinding': args.mode == 'delivery', 'sourceRevision': node['source_revision'], 'image': image,
            'architecture': args.architecture, 'runtimeSpecVersion': args.runtime_spec,
            'toolVersion': tools['version'], 'toolsSourceRevision': tools['sourceRevision'],
            'artifactSha256': values, 'binarySha256':values['binary'],'runtimeCodeSha256':values['runtimeWasm'],
            'agoraModuleSha256':values['agoraModule'],'genesis':r['genesis'],'network':r['package']['network'],'installedResolvedCommands': tools['installed'],
            'nodeProvenance': provenance, 'signingFingerprint': FINGERPRINT,
            'toolsMetadataSha256': tools['metadataSha256'], 'toolsChecksumsSha256': tools['checksumsSha256'],
            'harnessSha256': args.expected_harness_sha256, 'scope': 'disposable log-only enrollment; no live readiness/browser/strict-time claim'}

def parser():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('receipt', 'binary', 'runtime-wasm', 'agora-module', 'node-metadata', 'node-metadata-signature',
                 'node-checksums', 'node-checksums-signature', 'node-public-key', 'tools-release', 'tool-bin', 'harness', 'wrapper', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('node-binding', 'node-binding-signature', 'node-archive'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--expected-harness-sha256', required=True)
    p.add_argument('--expected-wrapper-sha256', required=True)
    p.add_argument('--architecture', choices=('amd64', 'arm64'), required=True)
    p.add_argument('--runtime-spec', type=int, required=True)
    p.add_argument('--mode', choices=('candidate', 'delivery'), required=True)
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    tools = authenticated_tools(args.tools_release, args.tool_bin)
    node, image, values, provenance = authenticated_node(args)
    result = assess_receipt(read_json(args.receipt), args, tools, node, image, values, provenance)
    result['receiptSha256'] = digest(args.receipt)
    result['nodeMetadataSha256'] = digest(args.node_metadata)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print('Authenticated private enrollment assessment written: ' + args.mode)

if __name__ == '__main__':
    main()
