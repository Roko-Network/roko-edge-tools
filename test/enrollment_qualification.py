#!/usr/bin/env python3
"""Offline controller/checker tests; no native fixture, services or network."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
checker = module('checker', ROOT / 'scripts/verify-enrollment-receipt.py')
harness = module('harness', ROOT / 'test/guarded_enrollment_live.py')
wrapper = module('wrapper', ROOT / 'test/run_guarded_enrollment_qualification.py')

class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir='/dev/shm', prefix='enrollment-checker-test-')
        self.root = Path(self.temporary.name)
        self.release = self.root / 'release'
        shutil.copytree(ROOT / 'test/fixtures/validator-enroll-1.4.5', self.release)
        self.package = self.root / 'installed/1.4.5'
        self.links = self.root / 'bin'
        self.links.mkdir()
        self.package.mkdir(parents=True)
        with tarfile.open(self.release / 'roko-validator-enroll-1.4.5.tar.gz') as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                relative = Path(member.name).relative_to('roko-validator-enroll-1.4.5')
                target = self.package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                target.chmod(member.mode)
        for name in checker.COMMANDS:
            (self.links / name).symlink_to(self.package / 'bin' / name)
    def tearDown(self):
        self.temporary.cleanup()
    def authenticate(self):
        # /dev/shm can be mounted noexec. Version-only output is independent from
        # actual signature/archive/path verification; never execute a fixture node.
        with mock.patch.object(checker.subprocess, 'run', wraps=checker.subprocess.run) as run:
            real = run._mock_wraps
            def calls(argv, **kwargs):
                if argv[0].endswith('/bin/roko-validator-enroll'):
                    return types.SimpleNamespace(stdout='roko-validator-enroll 1.4.5\n')
                return real(argv, **kwargs)
            run.side_effect = calls
            return checker.authenticated_tools(self.release, self.links)
    def test_actual_immutable_legacy_signatures_archive_and_installed_links_authenticate(self):
        tools = self.authenticate()
        self.assertEqual(tools['version'], '1.4.5')
        self.assertEqual(tools['compatibility']['runtime'], {'minimumSpecVersion':285,'maximumSpecVersion':287})
        self.assertEqual(tools['archiveSha256'], checker.LEGACY['archive'])
    def test_tampered_signed_manifest_rejected_before_digest_trust(self):
        path = self.release / 'SHA256SUMS'
        path.write_text(path.read_text() + 'tampered\n')
        with self.assertRaises(checker.VerificationError):
            self.authenticate()
    def test_invalid_metadata_signature_and_archive_rejected(self):
        path = self.release / 'roko-validator-enroll-1.4.5.metadata.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaises(checker.VerificationError):
            self.authenticate()
        shutil.copyfile(ROOT / 'test/fixtures/validator-enroll-1.4.5' / path.name, path)
        archive = self.release / 'roko-validator-enroll-1.4.5.tar.gz'
        archive.write_bytes(archive.read_bytes() + b'altered')
        with self.assertRaises(checker.VerificationError):
            self.authenticate()
    def test_symlink_escape_and_tampered_installed_library_refused(self):
        link = self.links / 'roko-session-key-window'
        link.unlink()
        outside = self.root / 'outside/bin/roko-session-key-window'
        outside.parent.mkdir(parents=True)
        outside.write_bytes((self.package / 'bin/roko-session-key-window').read_bytes())
        link.symlink_to(outside)
        with self.assertRaises(checker.VerificationError):
            self.authenticate()
        link.unlink(); link.symlink_to(self.package / 'bin/roko-session-key-window')
        path = self.package / 'lib/validator_enrollment.py'
        path.write_bytes(path.read_bytes() + b'\n# alteration\n')
        with self.assertRaises(checker.VerificationError):
            self.authenticate()

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.args = types.SimpleNamespace(runtime_spec=290, harness=ROOT / 'test/guarded_enrollment_live.py',
                                         expected_harness_sha256=checker.digest(ROOT / 'test/guarded_enrollment_live.py'),
                                         wrapper=ROOT / 'test/run_guarded_enrollment_qualification.py',expected_wrapper_sha256=checker.digest(ROOT / 'test/run_guarded_enrollment_qualification.py'),mode='candidate', architecture='amd64')
        self.values = {'binary':'a'*64,'runtimeWasm':'b'*64,'agoraModule':'c'*64}
        self.tools = {'version':'1.4.5','sourceRevision':checker.LEGACY['source'],
                      'files':{'bin/roko-session-key-window':'d'*64,'lib/validator_enrollment.py':'e'*64},
                      'installed':{'roko-validator-enroll':'/fixture/1.4.5/bin/roko-validator-enroll'},
                      'compatibility':{'runtime':{'minimumSpecVersion':285,'maximumSpecVersion':287}},
                      'metadataSha256':'f'*64,'checksumsSha256':'1'*64}
        network = {'chainName':'isolated development fixture','genesisHash':'0x'+'2'*64,'specName':'mainnet','specVersion':290,'transactionVersion':1,'metadataHash':'0x'+'3'*64}
        self.r = {'status':'pass','liveChainUsed':False,'genesis':network['genesisHash'],
                  'binarySha256':self.values['binary'],'runtimeCodeSha256':self.values['runtimeWasm'],
                  'expectedRuntimeSpec':290,'before':{'runtime':{'specVersion':290}},
                  'harnessSha256':self.args.expected_harness_sha256,'wrapperSha256':self.args.expected_wrapper_sha256,'toolVersion':'roko-validator-enroll 1.4.5',
                  'installedCommandLinks':True,'installedResolvedCommands':self.tools['installed'],
                  'helperSha256':'d'*64,'helperExit':0,'policyBytesRestored':True,
                  'afterPolicy':{'safeForNormalOperation':True},'package':{'network':network},
                  'keyCustodyEvidence':{'helperAttested':True,'method':'author_hasSessionKeys','validatorEnrollmentSha256':'e'*64},
                  'reuse':{'helperExit':0,'existingKeyCount':7,**{name:True for name in ('sameTuple','freshPackage','existingKeyFilesPreserved','safeAfter','policyBytesRestored')},
                           'custodyObservation':{'status':'independently-observed','method':'author_hasSessionKeys','observedTrue':True,'additionalUnsafeWindowOpened':False}},
                  'agoraImport':{label:{'accepted':True,'moduleSha256':'c'*64,'expected':network, 'rejected':{name:True for name in checker.NEGATIVE}} for label in ('generated','reused')},
                  'faultCases':[{'fault':fault,'helperExit':1,'existingKeyCount':7,**{name:True for name in ('safeAfter','policyBytesRestored','noPackageWritten','existingKeyFilesPreserved')}} for fault in checker.FAULTS],
                  **{name:True for name in ('processesStopped','serviceStopped','serviceRemoved','temporaryStateRemoved','campaignSliceStopped','campaignSliceRemoved','productionServiceIdentityPreserved')},
                  'cleanupErrors':[],'wrapperCleanupErrors':[],
                  'resources':{'verified':True,'sliceMemoryMax':12*1024**3,'sliceCpuQuotaPerSecUSec':4_000_000,'sliceTasksMax':1024,'runtimeMaxUSec':1_800_000_000,'timeoutStopUSec':90_000_000,'candidateMemoryMax':2*1024**3}}
    def assess(self):
        return checker.assess_receipt(self.r, self.args, self.tools, {'source_revision':'4'*40}, 'fixture@sha256:'+'5'*64, self.values, {'kind':'synthetic-test-only'})
    def test_candidate290_is_explicitly_not_a_published_delivery_binding(self):
        result = self.assess()
        self.assertTrue(result['outsidePublishedCompatibility'])
        self.assertFalse(result['deliveryBinding'])
        self.args.mode = 'delivery'
        with self.assertRaises(checker.VerificationError):self.assess()
    def test_all_six_negative_values_must_be_explicit_true_for_both_packages(self):
        for label in ('generated','reused'):
            for name in checker.NEGATIVE:
                for wrong in (False, 1, 'true', None):
                    changed=copy.deepcopy(self.r);changed['agoraImport'][label]['rejected'][name]=wrong
                    with self.assertRaises(checker.VerificationError):checker.assess_receipt(changed,self.args,self.tools,{'source_revision':'4'*40},'fixture@sha256:'+'5'*64,self.values,{})
    def test_each_fault_safe_key_and_cleanup_failure_refused(self):
        for key in ('safeAfter','policyBytesRestored','noPackageWritten','existingKeyFilesPreserved'):
            for index in range(3):
                changed=copy.deepcopy(self.r);changed['faultCases'][index][key]=False
                with self.assertRaises(checker.VerificationError):checker.assess_receipt(changed,self.args,self.tools,{'source_revision':'4'*40},'fixture@sha256:'+'5'*64,self.values,{})
        self.r['wrapperCleanupErrors']=['fixture failure']
        with self.assertRaises(checker.VerificationError):self.assess()
    def test_bool_exit_missing_tuple_or_fake_independent_custody_refused(self):
        self.r['helperExit']=False
        with self.assertRaises(checker.VerificationError):self.assess()
        self.r['helperExit']=0;self.r['reuse']['custodyObservation']['observedTrue']=False
        with self.assertRaises(checker.VerificationError):self.assess()
        self.r['reuse']['custodyObservation']['observedTrue']=True
        del self.r['package']['network']['metadataHash']
        with self.assertRaises(checker.VerificationError):self.assess()
    def test_new_release_cannot_inherit_the_old_runtime_range(self):
        self.tools['version']='1.4.6';self.r['toolVersion']='roko-validator-enroll 1.4.6';self.args.mode='delivery';self.args.runtime_spec=287
        self.r['expectedRuntimeSpec']=287;self.r['before']['runtime']['specVersion']=287
        for imported in self.r['agoraImport'].values(): imported['expected']['specVersion']=287
        with self.assertRaises(checker.VerificationError):self.assess()

class ResourceAndCustodyTests(unittest.TestCase):
    def test_owned_namespace_has_no_implicit_parent_slices_and_rejects_injection(self):
        name,slice_name,unit=wrapper.owned_names('abc123def456')
        self.assertNotIn('-',slice_name)
        self.assertEqual(unit,name+'-harness.service')
        with self.assertRaises(ValueError):wrapper.owned_names('abc;systemctl')
    def test_known_tuple_read_only_while_existing_unsafe_window_never_reopened(self):
        process=mock.Mock();process.poll.side_effect=[None,0];process.returncode=0;process.communicate.return_value=('','')
        with mock.patch.object(harness.subprocess,'Popen',return_value=process),mock.patch.object(harness,'run',return_value=types.SimpleNamespace(stdout='ROKO_RPC_METHODS=Unsafe\n'))as run,mock.patch.object(harness,'rpc',return_value=True)as rpc:
            _, observation=harness.observe_custody_window(['fixture-helper'],9944,Path('/fixture/policy'),'0xpublic')
            self.assertEqual(observation['status'],'independently-observed')
            rpc.assert_called_once_with(9944,'author_hasSessionKeys',['0xpublic'])
            self.assertEqual(run.call_args.args,('sudo','-n','cat','/fixture/policy'))
    def test_closed_window_records_only_helper_attestation_and_no_unsafe_rpc(self):
        process=mock.Mock();process.poll.return_value=0;process.returncode=0;process.communicate.return_value=('','')
        with mock.patch.object(harness.subprocess,'Popen',return_value=process),mock.patch.object(harness,'rpc')as rpc:
            _, observation=harness.observe_custody_window(['fixture-helper'],9944,Path('/fixture/policy'),'0xpublic')
            self.assertEqual(observation['status'],'helper-attested-window-closed')
            self.assertFalse(observation['observedTrue']);rpc.assert_not_called()
    def test_false_custody_rejected_and_owned_helper_terminated(self):
        process=mock.Mock();process.poll.side_effect=[None,None];process.pid=123
        with mock.patch.object(harness.subprocess,'Popen',return_value=process),mock.patch.object(harness,'run',return_value=types.SimpleNamespace(stdout='ROKO_RPC_METHODS=Unsafe\n'))as run,mock.patch.object(harness,'rpc',return_value=False):
            with self.assertRaises(ValueError):harness.observe_custody_window(['fixture-helper'],9944,Path('/fixture/policy'),'0xpublic')
            self.assertIn(mock.call('sudo','-n','kill','-TERM','--','-123'),run.call_args_list)


class NodeBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/dev/shm',prefix='enrollment-role-test-');self.root=Path(self.tmp.name)
        self.paths={role:self.root/name for role,name in [('binary','roko-node'),('runtimeWasm','production.wasm'),('agoraModule','agora.mjs')]}
        for role,path in self.paths.items():path.write_bytes(('synthetic-'+role).encode())
        self.paths['binary'].write_bytes(b'\x7fELF\x02\x01'+b'\x00'*12+(62).to_bytes(2,'little')+b'synthetic-not-executable')
        self.metadata=self.root/'BUILD-METADATA.json';self.metadata.write_text(json.dumps({'source_revision':'a'*40,'images':{'amd64':'fixture@sha256:'+'b'*64}}))
        self.sums=self.root/'SHA256SUMS';self.write_sums()
        self.args=types.SimpleNamespace(node_metadata=self.metadata,node_metadata_signature=self.root/'metadata.asc',node_checksums=self.sums,node_checksums_signature=self.root/'sums.asc',node_public_key=ROOT/'release/roko-release-signing-key.asc',architecture='amd64',binary=self.paths['binary'],runtime_wasm=self.paths['runtimeWasm'],agora_module=self.paths['agoraModule'],node_binding=None,node_binding_signature=None,node_archive=None)
    def tearDown(self):self.tmp.cleanup()
    def write_sums(self,other=None):
        paths=[self.metadata]+(list(self.paths.values()) if other is None else other)
        self.sums.write_text(''.join(checker.digest(path)+'  '+path.name+'\n' for path in paths))
    def test_direct_signed_checksum_coverage_requires_every_exact_role(self):
        with mock.patch.object(checker,'verify_signature')as verified:
            _,_,_,provenance=checker.authenticated_node(self.args)
            self.assertEqual(verified.call_count,2);self.assertEqual(provenance['kind'],'direct-signed-checksum-coverage')
            self.paths['runtimeWasm'].write_bytes(b'altered')
            with self.assertRaises(checker.VerificationError):checker.authenticated_node(self.args)
    def test_signed_operator_archive_derivation_is_explicit_and_checks_actual_member(self):
        archive=self.root/'roko-node-testnet-native-amd64.tar.gz'
        with tarfile.open(archive,'w:gz')as bundle:bundle.add(self.paths['binary'],arcname='roko-node')
        self.write_sums([archive]);binding=self.root/'binding.json'
        value={'schema':'roko.enrollment-artifact-attestation.v1','issuer':'roko-operator-private-qualification','sourceRevision':'a'*40,'sourceTree':'c'*40,'architecture':'amd64','image':'fixture@sha256:'+'b'*64,'releaseMetadataSha256':checker.digest(self.metadata),'releaseChecksumsSha256':checker.digest(self.sums),'roles':{role:{'path':str(path),'sha256':checker.digest(path),'derivation':{'binary':'signed-native-archive','runtimeWasm':'independently-reproduced-production','agoraModule':'exact-source-export'}[role]}for role,path in self.paths.items()}}
        value['roles']['binary'].update(archiveSha256=checker.digest(archive),archiveMember='roko-node');binding.write_text(json.dumps(value));self.args.node_binding=binding;self.args.node_binding_signature=self.root/'binding.asc';self.args.node_archive=archive
        with mock.patch.object(checker,'verify_signature')as verified:
            _,_,_,provenance=checker.authenticated_node(self.args)
            self.assertEqual(verified.call_count,3);self.assertEqual(provenance['issuer'],'roko-operator-private-qualification')
            value['roles']['binary']['archiveMember']='../roko-node';binding.write_text(json.dumps(value))
            with self.assertRaises(checker.VerificationError):checker.authenticated_node(self.args)

class ResourceContractTests(unittest.TestCase):
    def test_harness_requires_real_exact_outer_owner_and_numeric_caps(self):
        name='roko-enrollment-qualification-abc123def456';slice_name='rokoenrollqualabc123def456.slice'
        values={'MemoryMax':str(12*1024**3),'CPUQuotaPerSecUSec':'4s','TasksMax':'1024','ControlGroup':'/'+slice_name}
        outer={'Slice':slice_name,'RuntimeMaxUSec':'30min','TimeoutStopUSec':'1min 30s','MainPID':str(os.getpid())}
        with mock.patch.object(harness,'systemd_properties',side_effect=[values,outer]),mock.patch.object(Path,'read_text',return_value='0::/'+slice_name+'/'+name+'-harness.service\n'):
            self.assertTrue(harness.campaign_resources(name,slice_name)['verified'])
        wrong=dict(outer,MainPID='1')
        with mock.patch.object(harness,'systemd_properties',side_effect=[values,wrong]):
            with self.assertRaises(ValueError):harness.campaign_resources(name,slice_name)
        wrong=dict(values,MemoryMax='max')
        with mock.patch.object(harness,'systemd_properties',side_effect=[wrong,outer]):
            with self.assertRaises(ValueError):harness.campaign_resources(name,slice_name)

if __name__ == '__main__':unittest.main()
