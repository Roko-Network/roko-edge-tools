#!/usr/bin/env python3
"""Offline profile checks; synthetic delivery inputs are not native evidence."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qualification_tests', ROOT / 'test/enrollment_qualification.py')
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)
checker = qualification.checker


def profile():
    return json.loads((ROOT / 'release/validator-enroll-compatibility.template.json').read_text()
                      .replace('@VERSION@', '1.4.7').replace('@SOURCE_REVISION@', '1' * 40))


class VersionProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = profile()
        self.row, = self.profile['node']['qualifiedBuilds']
        self.evidence = json.loads((ROOT / 'docs/evidence/guarded-fba4-private146-runtime290-20261015.json').read_text())

    def test_source_commands_and_profile_version_agree(self):
        self.assertEqual((ROOT / 'VERSION').read_text().strip(), '1.4.7')
        for command in ('roko-validator-enroll',):
            output = subprocess.check_output([str(ROOT / 'bin' / command), '--version'], text=True).strip()
            self.assertEqual(output, command + ' 1.4.7')
        self.assertEqual(self.profile['tool']['version'], '1.4.7')

    def test_exact_candidate_amd64_node_and_runtime_match_historical_evidence(self):
        self.assertEqual(self.profile['runtime'], {'minimumSpecVersion': 290, 'maximumSpecVersion': 290})
        self.assertEqual(self.row['platform'], 'linux-amd64')
        self.assertEqual(self.row['releaseId'], 'nightly-fba4e76c-20261015')
        self.assertEqual(self.row['sourceRevision'], self.evidence['sourceRevision'])
        self.assertEqual(self.row['binarySha256'], self.evidence['artifactSha256']['binary'])
        self.assertEqual('roko-node ' + self.row['displayVersion'], self.evidence['binaryVersion'])
        self.assertEqual(self.row['runtimeSpecVersion'], self.evidence['observedNetwork']['specVersion'])
        self.assertEqual(self.profile['updatedAt'], self.evidence['preparedAtUtc'])
        self.assertEqual(dt.datetime.fromisoformat(self.profile['updatedAt'].replace('Z', '+00:00')).date(), dt.date(2026, 10, 16))
        for name in ('evidenceUrl', 'reuseEvidenceUrl'):
            relative = self.row[name].split('/blob/' + '1' * 40 + '/', 1)[1]
            self.assertTrue((ROOT / relative).is_file())

    def test_projection_keeps_private_historical_scope_and_new147_pending(self):
        self.assertEqual(self.evidence['testedToolVersion'], '1.4.6')
        self.assertEqual(self.evidence['testedToolsSourceRevision'], '0b489f73e340ebba1f78c63bbd5554f76bb7e722')
        self.assertTrue(self.evidence['deliveryBinding'])
        self.assertFalse(self.evidence['publicToolRelease'])
        self.assertFalse(self.evidence['qualificationAppliesTo147'])
        self.assertEqual(self.evidence['proposedToolVersion'], '1.4.7')
        self.assertEqual(self.evidence['public146HasDifferentSource'], '35112c97ab820a8e1ffeb7fcd9932eecda76fa93')
        self.assertFalse(self.evidence['liveChainUsed'])
        self.assertIn('unpublished', self.evidence['proposedReleaseStatus'])
        for result in self.evidence['agora'].values():
            self.assertTrue(result['accepted'])
            self.assertEqual(set(result['rejected']), checker.NEGATIVE)
            self.assertTrue(all(v is True for v in result['rejected'].values()))
            self.assertEqual(result['rejectionCodes'], {'wrongGenesis': 'network.genesisHash', 'wrongRuntime': 'network.specVersion',
                                                       'wrongMetadata': 'network.metadataHash', 'expired': 'time.expired',
                                                       'tampered': 'integrity.mismatch', 'replayed': 'integrity.replay'})
        self.assertEqual({row['fault'] for row in self.evidence['faultCases']}, checker.FAULTS)
        for row in self.evidence['faultCases']:
            self.assertEqual(row['existingKeyCount'], 7)
            self.assertTrue(row['existingKeyFilesPreserved'])
            self.assertTrue(row['noPackageWritten'])

    def test_projection_excludes_internal_paths_hostnames_and_addresses(self):
        text = json.dumps(self.evidence).lower()
        for value in ('/home/', '/run/', '/dev/', '10.0.42.', '127.0.0.1', 'noodle', 'titan', 'integrolabs', 'openbao', 'gnupghome', 'stagepath', 'installedresolvedcommands'):
            self.assertNotIn(value, text)
        self.assertNotRegex(text, r'\b(?:10|127)\.\d+\.\d+\.\d+\b|\b192\.168\.\d+\.\d+\b|\b172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+\b')

    def test_immutable_145_archive_and_legacy_support_are_retained(self):
        fixture = ROOT / 'test/fixtures/validator-enroll-1.4.5'
        self.assertEqual(checker.digest(fixture / 'roko-validator-enroll-1.4.5.tar.gz'), checker.LEGACY['archive'])
        self.assertEqual(checker.digest(fixture / 'roko-validator-enroll-1.4.5.metadata.json'), checker.LEGACY['metadata'])
        self.assertEqual(checker.LEGACY['version'], '1.4.5')


class SyntheticDeliveryProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = qualification.ReceiptTests()
        self.fixture.setUp()
        self.fixture.args.mode = 'delivery'
        self.fixture.tools['version'] = '1.4.7'
        self.fixture.tools['compatibility'] = profile()
        self.row = self.fixture.tools['compatibility']['node']['qualifiedBuilds'][0]
        self.fixture.r['toolVersion'] = 'roko-validator-enroll 1.4.7'
        self.fixture.r['binaryVersion'] = 'roko-node ' + self.row['displayVersion']
        self.fixture.values['binary'] = self.row['binarySha256']
        self.fixture.r['binarySha256'] = self.row['binarySha256']
        # Delivery binds the exact proposed runtime; retarget the synthetic tuple.
        spec = self.row['runtimeSpecVersion']
        self.fixture.args.runtime_spec = spec
        self.fixture.r['expectedRuntimeSpec'] = spec
        self.fixture.r['before']['runtime']['specVersion'] = spec
        self.fixture.r['package']['network']['specVersion'] = spec
        for imported in self.fixture.r['agoraImport'].values():
            imported['expected']['specVersion'] = spec

    def assess(self):
        f = self.fixture
        return checker.assess_receipt(f.r, f.args, f.tools,
                                      {'source_revision': 'fba4e76cfeb062bcba0cc2c2fd16f9d9b23c275b'},
                                      'synthetic-image@sha256:' + '5' * 64, f.values,
                                      {'kind': 'synthetic-test-only-not-native-evidence'})

    def test_exact_profile_is_accepted_by_unchanged_delivery_checker(self):
        result = self.assess()
        self.assertTrue(result['deliveryBinding'])
        self.assertFalse(result['outsidePublishedCompatibility'])

    def test_source_binary_architecture_runtime_and_display_substitutions_refused(self):
        for field, wrong in {'sourceRevision': '0' * 40, 'binarySha256': '0' * 64,
                             'platform': 'linux-arm64', 'runtimeSpecVersion': 286,
                             'displayVersion': '3.0.0-dev-other'}.items():
            original = self.row[field]
            self.row[field] = wrong
            with self.subTest(field=field), self.assertRaises(checker.VerificationError):
                self.assess()
            self.row[field] = original

    def test_duplicate_pair_or_inherited_runtime_range_refused(self):
        rows = self.fixture.tools['compatibility']['node']['qualifiedBuilds']
        rows.append(copy.deepcopy(self.row))
        with self.assertRaises(checker.VerificationError):
            self.assess()
        rows.pop()
        self.fixture.tools['compatibility']['runtime']['minimumSpecVersion'] = 285
        with self.assertRaises(checker.VerificationError):
            self.assess()


class Published146BaselineTests(unittest.TestCase):
    """Actual public release bytes, not a replacement private146 build."""
    def setUp(self):
        self.root = ROOT / 'test/fixtures/validator-enroll-1.4.6'

    def test_public146_signatures_and_signed_members_remain_exact(self):
        self.assertEqual(checker.digest(self.root / 'SHA256SUMS'), '1030c9a76bd867b9893b830829e7fa21895e7732aa47ce94926ee67475c35919')
        self.assertEqual(checker.digest(self.root / 'roko-validator-enroll-1.4.6.metadata.json'), 'c9447eb76fe8240aaab76a1205ed9d73a7f9c095f5ff4b951aff9898cc4f0f16')
        for name in ('SHA256SUMS', 'roko-validator-enroll-1.4.6.metadata.json'):
            checker.verify_signature(self.root / name, self.root / (name + '.asc'), self.root / 'roko-release-signing-key.asc')
        for name, digest in checker.checksums(self.root / 'SHA256SUMS').items():
            self.assertEqual(checker.digest(self.root / name), digest)

    def test_public146_retains_exact286_pair_and_distinct_source(self):
        archive = self.root / 'roko-validator-enroll-1.4.6.tar.gz'
        self.assertEqual(checker.digest(archive), 'ab78ac289d0c712ca636d75e687b8f7f0ea814f98b3a6307c74137e42cb6dbd8')
        with tarfile.open(archive) as bundle:
            raw = bundle.extractfile('roko-validator-enroll-1.4.6/compatibility/validator-enroll-compatibility.json').read()
        value = json.loads(raw)
        self.assertEqual(value['tool']['sourceRevision'], '35112c97ab820a8e1ffeb7fcd9932eecda76fa93')
        self.assertEqual(value['runtime'], {'minimumSpecVersion': 286, 'maximumSpecVersion': 286})
        row, = value['node']['qualifiedBuilds']
        self.assertEqual(row['sourceRevision'], 'f490bcd12df8af67e9bd009482fbc1954199d7f1')
        self.assertEqual(row['binarySha256'], 'b0ddc0fdae81ce09b1f6c9b18eee61f86ab6d35ec53b825bcfcc77acf3e66fdc')
        self.assertNotEqual(row['sourceRevision'], profile()['node']['qualifiedBuilds'][0]['sourceRevision'])


if __name__ == '__main__':
    unittest.main()
