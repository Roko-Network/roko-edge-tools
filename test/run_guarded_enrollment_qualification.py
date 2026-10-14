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

def execute(args):
    if hashlib.sha256(HARNESS.read_bytes()).hexdigest() != args.expected_harness_sha256:
        raise ValueError('reviewed harness hash mismatch')
    receipt = args.receipt.absolute()
    if receipt.exists() or receipt.is_symlink():
        raise ValueError('receipt must be a new path')
    forwarded = args.harness_args
    if forwarded and forwarded[0] == '--':
        forwarded = forwarded[1:]
    if not forwarded or any(arg.split('=', 1)[0] in ('--campaign-name', '--campaign-slice', '--receipt') for arg in forwarded):
        raise ValueError('wrapper owns campaign and receipt arguments')
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
    production = run('systemctl', 'show', 'roko-node.service', '--property=MainPID', '--property=ControlGroup').stdout
    if any(line.split('=', 1)[-1].startswith('/' + slice_name) for line in production.splitlines()):
        raise ValueError('production service unexpectedly inside campaign')
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
            production_after = run('systemctl', 'show', 'roko-node.service', '--property=MainPID', '--property=ControlGroup').stdout
            if production_after != production:
                errors.append('production-service-identity-changed')
            if receipt.exists() and not receipt.is_symlink():
                value = json.loads(receipt.read_text())
                value['campaignSliceStopped'], value['campaignSliceRemoved'] = stopped, removed
                value['productionServiceIdentityPreserved'] = production_after == production
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-harness-sha256', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('harness_args', nargs=argparse.REMAINDER)
    execute(parser.parse_args(argv))

if __name__ == '__main__':
    main()
