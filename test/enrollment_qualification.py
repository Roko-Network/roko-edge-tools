#!/usr/bin/env python3
"""Offline controller/checker tests; no native fixture, services or network."""
import copy
import datetime as dt
import contextlib
import io
import subprocess
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

    def test_extra_importable_bytecode_and_symlink_files_refused(self):
        for relative, link in [('lib/unsigned.py', False), ('lib/__pycache__/validator_enrollment.pyc', False), ('lib/unsigned-link.py', True)]:
            with self.subTest(relative=relative):
                path = self.package / relative
                path.parent.mkdir(exist_ok=True)
                if link: path.symlink_to(self.package / 'lib/validator_enrollment.py')
                else: path.write_bytes(b'unsigned')
                with self.assertRaises(checker.VerificationError): self.authenticate()
                path.unlink()
                if path.parent.name == '__pycache__': path.parent.rmdir()
        empty = self.package / 'lib/__pycache__'; empty.mkdir()
        with self.assertRaises(checker.VerificationError): self.authenticate()

    def test_archive_must_bind_every_command_before_version_execution(self):
        # Model a future signature-verified archive missing a command. Keep all
        # other authentication real; changing the retained signed archive would
        # correctly fail its digest earlier instead of exercising this boundary.
        real_open = checker.tarfile.open
        for command in checker.COMMANDS:
            with real_open(self.release / 'roko-validator-enroll-1.4.5.tar.gz') as archive:
                members = [m for m in archive.getmembers() if not m.name.endswith('/bin/' + command)]
                with self.subTest(command=command), mock.patch.object(archive, 'getmembers', return_value=members), mock.patch.object(checker.tarfile, 'open', return_value=archive):
                    with self.assertRaisesRegex(checker.VerificationError, 'all four installed commands'): self.authenticate()

    def test_version_invocation_disables_installed_bytecode(self):
        with mock.patch.object(checker.subprocess, 'run', wraps=checker.subprocess.run) as run:
            real = run._mock_wraps
            def calls(argv, **kwargs):
                if argv[0].endswith('/bin/roko-validator-enroll'):
                    self.assertEqual(kwargs['env']['PYTHONDONTWRITEBYTECODE'], '1')
                    return types.SimpleNamespace(stdout='roko-validator-enroll 1.4.5\n')
                return real(argv, **kwargs)
            run.side_effect = calls
            checker.authenticated_tools(self.release, self.links)

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
                  'afterPolicy':{'safeForNormalOperation':True},'package':{'network':copy.deepcopy(network)},
                  'keyCustodyEvidence':{'helperAttested':True,'method':'author_hasSessionKeys','validatorEnrollmentSha256':'e'*64},
                  'reuse':{'helperExit':0,'existingKeyCount':7,**{name:True for name in ('sameTuple','freshPackage','existingKeyFilesPreserved','safeAfter','policyBytesRestored')},
                           'custodyObservation':{'status':'independently-observed','method':'author_hasSessionKeys','observedTrue':True,'additionalUnsafeWindowOpened':False}},
                  'agoraImport':{label:{'accepted':True,'moduleSha256':'c'*64,'expected':copy.deepcopy(network), 'rejected':{name:True for name in checker.NEGATIVE}} for label in ('generated','reused')},
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

    def test_every_package_network_field_bound_to_independent_expected(self):
        wrong = {'chainName':'other', 'genesisHash':'0x'+'9'*64, 'specName':'other',
                 'specVersion':291, 'transactionVersion':2, 'metadataHash':'0x'+'8'*64}
        for field, value in [*wrong.items(), ('transactionVersion', True)]:
            changed = copy.deepcopy(self.r)
            observed = copy.deepcopy(changed['agoraImport'])
            changed['package']['network'][field] = value
            self.assertEqual(changed['agoraImport'], observed)
            with self.subTest(field=field), self.assertRaisesRegex(checker.VerificationError, 'network tuple mismatch'):
                checker.assess_receipt(changed,self.args,self.tools,{'source_revision':'4'*40},'fixture@sha256:'+'5'*64,self.values,{})

class AgoraEmitterTests(unittest.TestCase):
    def test_actual_js_emitter_and_exact_export_produce_checker_booleans(self):
        existing = module('existing_enrollment_tests', ROOT / 'test/validator_enrollment.py')
        fixture = existing.ValidatorEnrollmentTests()
        fixture.setUp()
        try:
            fixture.now = dt.datetime.now(dt.timezone.utc)
            genesis = '0x' + '2'*64
            rpc = existing.FakeRpc({('chain_getBlockHash',(0,)):genesis,
                                    ('state_getRuntimeVersion',()):{'specName':'mainnet','specVersion':290,'transactionVersion':1}})
            package = fixture.build(rpc, fixture.args(expected_genesis=genesis))
            path = ROOT / 'test/fixtures/agora-validator/validator-enrollment.mjs'
            provenance = json.loads(path.with_name('SOURCE.json').read_text())
            self.assertEqual(checker.digest(path), provenance['sha256'])
            result = subprocess.run(['node', str(ROOT / 'test/agora_enrollment_contract.mjs'), str(path), provenance['sha256']],
                                    input=json.dumps({'package':package,'expected':package['network']}),
                                    capture_output=True,text=True,check=True,timeout=15)
            value = json.loads(result.stdout)
            self.assertIs(value['accepted'], True)
            self.assertEqual(set(value['rejected']), checker.NEGATIVE)
            self.assertTrue(all(value['rejected'][name] is True for name in checker.NEGATIVE))
            self.assertEqual(value['rejectionCodes'], {'wrongGenesis':'network.genesisHash','wrongRuntime':'network.specVersion',
                            'wrongMetadata':'network.metadataHash','expired':'time.expired','tampered':'integrity.mismatch','replayed':'integrity.replay'})
            assessment = ReceiptTests(); assessment.setUp()
            assessment.r['genesis'] = genesis
            assessment.r['package']['network'] = copy.deepcopy(package['network'])
            assessment.values['agoraModule'] = provenance['sha256']
            for label in ('generated','reused'):
                assessment.r['agoraImport'][label] = copy.deepcopy(value)
            self.assertFalse(assessment.assess()['deliveryBinding'])
            with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
                wrong_module = Path(tmp) / 'wrong-code.mjs'
                wrong_module.write_bytes(path.read_bytes().replace(b'network.genesisHash', b'network.unexpected'))
                failed = subprocess.run(['node',str(ROOT / 'test/agora_enrollment_contract.mjs'),str(wrong_module),checker.digest(wrong_module)],
                                        input=json.dumps({'package':package,'expected':package['network']}),capture_output=True,text=True,timeout=15)
                self.assertNotEqual(failed.returncode,0)
                self.assertEqual(failed.stdout,'')
        finally:
            fixture.tearDown()

class ParserBoundaryTests(unittest.TestCase):
    forwarded = ['--binary','/fixture/node','--expected-sha256','a'*64,'--runtime-wasm','/fixture/runtime',
                 '--expected-runtime-sha256','b'*64,'--expected-runtime-spec','290','--tool-bin','/fixture/bin']
    def test_real_harness_parser_refuses_owned_abbreviations(self):
        owned = ['--campaign-name','owned','--campaign-slice','owned.slice','--receipt','/fixture/receipt']
        for bad in ('--campaign-n=other', '--campaign-s=other.slice', '--rec=/other'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                harness.argument_parser().parse_args(owned + self.forwarded + [bad])
    def test_wrapper_rejects_abbreviations_exact_duplicates_and_double_dash_before_services(self):
        for bad in ('--campaign-n=other','--campaign-s=other.slice','--rec=/other','--campaign-name=other',
                    '--campaign-slice=other.slice','--receipt=/other','--','--receipt'):
            with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
                args = ['--expected-harness-sha256',checker.digest(wrapper.HARNESS),'--receipt',str(Path(tmp)/'receipt'),'--',*self.forwarded,bad]
                with mock.patch.object(wrapper,'run') as run, mock.patch.object(wrapper.subprocess,'run') as process:
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises((SystemExit,ValueError)):
                        wrapper.main(args)
                    run.assert_not_called(); process.assert_not_called()
        with mock.patch.object(wrapper,'execute') as execute:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                wrapper.main(['--expected-harness-sha256','a'*64,'--rec','/other'])
            execute.assert_not_called()
    def test_tool_and_privileged_helper_environments_disable_bytecode(self):
        with mock.patch.object(harness.subprocess,'run') as run:
            harness.run('/fixture/tool', '--version')
            self.assertEqual(run.call_args.kwargs['env']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertEqual(harness.privileged_tool('roko-session-key-window')[:4],
                         ['sudo','-n','env','PYTHONDONTWRITEBYTECODE=1'])

    def test_harness_refuses_preexisting_cache_before_privileged_calls(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            root = Path(tmp); binary = root/'node'; wasm = root/'runtime.wasm'
            binary.write_bytes(b'offline-not-executable'); wasm.write_bytes(b'offline-wasm')
            installed = root/'installed'; (installed/'bin').mkdir(parents=True)
            (installed/'bin/roko-validator-enroll').write_text('not executed')
            (installed/'lib/__pycache__').mkdir(parents=True)
            with mock.patch.object(harness,'TOOL_BIN',installed/'bin'), mock.patch.object(harness,'run') as run:
                with self.assertRaisesRegex(ValueError,'preexisting unsigned installed bytecode'):
                    harness.qualify(binary,checker.digest(binary),root/'receipt',wasm,checker.digest(wasm),290)
                run.assert_not_called()

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
