#!/usr/bin/env python3
"""Root-controlled opt-in resource wrapper; never use on an occupied fixture lane.

Starts only uniquely named owned units. The harness inherits the finite outer
service cgroup; the candidate joins the same aggregate slice. No fixture is
executed by importing this module or running --help.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/guarded_enrollment_live.py'

def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, capture_output=True, text=True,
                          timeout=kwargs.pop('timeout', 30), **kwargs)

def owned_names(identifier):
    if not re.fullmatch(r'[0-9a-f]{12}', identifier):
        raise ValueError('invalid owned campaign identifier')
    name = 'roko-enrollment-qualification-' + identifier
    return name, 'rokoenrollqual' + identifier + '.slice', name + '-harness.service'

def unit_inode(path):
    return run('sudo', '-n', 'stat', '--printf=%d:%i:%u', '--', str(path)).stdout

def production_service_name(value):
    if not re.fullmatch(r'roko-[a-z0-9]+(?:-[a-z0-9]+)*\.service', value):
        raise ValueError('production service must be an exact managed ROKO service name')
    return value

def production_snapshot(unit):
    production_service_name(unit)
    fields = ('Id', 'LoadState', 'ActiveState', 'MainPID', 'ControlGroup')
    text = run('systemctl', 'show', unit, *['--property=' + field for field in fields]).stdout
    lines = [line.split('=', 1) for line in text.splitlines()]
    if len(lines) != len(fields) or any(len(line) != 2 for line in lines):
        raise ValueError('production service properties incomplete')
    state = dict(lines)
    if set(state) != set(fields) or not re.fullmatch(r'[0-9]+', state['MainPID']):
        raise ValueError('production service properties invalid')
    state['MainPID'] = int(state['MainPID'])
    return state

def validate_production_snapshot(unit, state, slice_name):
    production_service_name(unit)
    group = state.get('ControlGroup')
    if (state.get('Id') != unit or state.get('LoadState') != 'loaded'
            or state.get('ActiveState') != 'active' or type(state.get('MainPID')) is not int
            or state['MainPID'] <= 0 or not isinstance(group, str) or not group.startswith('/')
            or group == '/' or any(character.isspace() for character in group)
            or slice_name in group.split('/')):
        raise ValueError('production service must be loaded, active and outside the campaign with its exact identity')


def execute(args):
    source = HARNESS.read_bytes()
    if hashlib.sha256(source).hexdigest() != args.expected_harness_sha256:
        raise ValueError('reviewed harness hash mismatch')
    receipt = args.receipt.absolute()
    if receipt.exists() or receipt.is_symlink():
        raise ValueError('receipt must be a new path')
    forwarded = args.harness_args
    if forwarded and forwarded[0] == '--':
        forwarded = forwarded[1:]
    if not forwarded or '--' in forwarded or any(arg.split('=', 1)[0] in ('--campaign-name', '--campaign-slice', '--receipt', '--production-service') for arg in forwarded):
        raise ValueError('wrapper owns campaign and receipt arguments')
    # Parse the real harness grammar before any service operation. Abbreviations
    # and option terminators cannot replace wrapper-owned values.
    namespace = {'__file__': str(HARNESS), '__name__': 'qualification_preflight'}
    # Compile the already hash-checked bytes; no stale source-tree .pyc import.
    exec(compile(source, str(HARNESS), 'exec'), namespace)
    namespace['argument_parser']().parse_args(['--campaign-name', 'preflight', '--campaign-slice',
                                 'preflight.slice', '--receipt', str(receipt), *forwarded])
    operator_uid = os.getuid()
    if operator_uid == 0:
        operator_uid = int(os.environ.get('SUDO_UID', '0'))
    if operator_uid <= 0:
        raise ValueError('run through a non-root operator with scoped sudo')
    operator = pwd.getpwuid(operator_uid)
    name, slice_name, outer = owned_names(uuid.uuid4().hex[:12])
    path = Path('/run/systemd/system') / slice_name
    if path.exists() or path.is_symlink():
        raise ValueError('owned slice path already exists')
    production = production_snapshot(args.production_service)
    validate_production_snapshot(args.production_service, production, slice_name)
    installed, inode, errors = False, None, []
    try:
        with tempfile.TemporaryDirectory(prefix=name + '-', dir='/dev/shm') as temporary:
            source = Path(temporary) / slice_name
            source.write_text('[Unit]\nDescription=Owned disposable ROKO enrollment campaign\n'
                              '[Slice]\nMemoryMax=12G\nCPUQuota=400%\nTasksMax=1024\n')
            run('sudo', '-n', 'install', '-m', '0644', str(source), str(path))
            installed, inode = True, unit_inode(path)
            if not inode.endswith(':0'):
                raise ValueError('slice file is not root-owned')
            run('sudo', '-n', 'systemctl', 'daemon-reload')
            command = ['sudo', '-n', 'systemd-run', '--wait', '--collect', '--service-type=exec',
                       '--unit=' + outer, '--slice=' + slice_name, '--uid=' + operator.pw_name,
                       '--property=RuntimeMaxSec=1800', '--property=TimeoutStopSec=90',
                       '--property=KillMode=mixed', '--property=WorkingDirectory=' + str(ROOT),
                       '--property=LimitCORE=0', '--setenv=PATH=' + os.environ['PATH'],
                       '--setenv=PYTHONDONTWRITEBYTECODE=1',
                       '/usr/bin/python3', str(HARNESS), '--campaign-name', name,
                       '--campaign-slice', slice_name, '--receipt', str(receipt), *forwarded]
            result = subprocess.run(command, capture_output=True, text=True, timeout=1905)
            if result.returncode:
                errors.append('harness-service-failed:' + str(result.returncode))
    except BaseException:
        errors.append('wrapper-interrupted-or-failed')
        raise
    finally:
        if installed:
            # Exact owned units only. Slice teardown catches authority children and
            # candidate even when the harness was forcibly stopped at its deadline.
            for unit in (outer, name + '-candidate.service', slice_name):
                try:
                    run('sudo', '-n', 'systemctl', 'stop', unit, timeout=90)
                except subprocess.CalledProcessError:
                    active = subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0
                    if active:
                        errors.append('owned-unit-stop-failed:' + unit)
            try:
                if unit_inode(path) != inode or path.is_symlink():
                    raise ValueError('slice ownership changed; refusing removal')
                run('sudo', '-n', 'rm', '--', str(path))
                run('sudo', '-n', 'systemctl', 'daemon-reload')
                # --collect can unload the completed transient outer service.
                # Reset only an extant failed unit; absence is successful cleanup.
                for owned in (outer, name + '-candidate.service', slice_name):
                    state = run('systemctl', 'show', owned, '--property=ActiveState').stdout.strip()
                    if state == 'ActiveState=failed':
                        run('sudo', '-n', 'systemctl', 'reset-failed', owned)
            except Exception:
                errors.append('owned-slice-removal-failed')
            stopped = subprocess.run(['systemctl', 'is-active', '--quiet', slice_name]).returncode != 0
            removed = not path.exists()
            production_after, preserved = None, False
            try:
                production_after = production_snapshot(args.production_service)
                validate_production_snapshot(args.production_service, production_after, slice_name)
                preserved = production_after == production
            except Exception:
                errors.append('production-service-after-validation-failed')
            if not preserved:
                errors.append('production-service-identity-changed')
            if receipt.exists() and not receipt.is_symlink():
                value = json.loads(receipt.read_text())
                value['campaignSliceStopped'], value['campaignSliceRemoved'] = stopped, removed
                value['productionServiceIdentityPreserved'] = preserved
                value['productionService'] = {'unit': args.production_service, 'before': production, 'after': production_after}
                value['wrapperSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                value['wrapperCleanupErrors'] = errors
                if errors or not stopped or not removed:
                    value['status'] = 'failed'
                # Evidence belongs to the operator; never follow a receipt link.
                descriptor = os.open(receipt, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                with os.fdopen(descriptor, 'w') as out:
                    out.write(json.dumps(value, indent=2) + '\n')
            if errors or not stopped or not removed:
                raise RuntimeError('owned campaign did not complete cleanly')
    if not receipt.is_file():
        raise RuntimeError('harness produced no receipt')
    print('Owned enrollment fixture receipt: ' + str(receipt))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--expected-harness-sha256', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--production-service', type=production_service_name, required=True)
    parser.add_argument('harness_args', nargs=argparse.REMAINDER)
    execute(parser.parse_args(argv))

if __name__ == '__main__':
    main()
