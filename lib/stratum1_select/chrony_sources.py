"""Render, install and reload a Chrony sources file for selected stratum-1 servers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

CHRONY_CONFS = ("/etc/chrony/chrony.conf", "/etc/chrony.conf")
SOURCES_FILENAME = "roko-stratum1.sources"
CHILD_ENV = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


class InstallBlocked(Exception):
    """Installing the sources file is not possible on this host as configured."""


def render_sources(chosen: list[dict], generated_at: str, version: str) -> str:
    lines = [
        f"# Managed by roko-stratum1-select {version}; regenerate with: sudo roko-stratum1-select --install",
        f"# Nearest stratum-1 servers measured from this host at {generated_at}.",
        "# Adds sources only: keep your other Chrony sources so at least two stay selectable.",
    ]
    for server in chosen:
        lines.append(f"# {server['host']}: {server.get('operator') or 'operator-supplied'}, "
                     f"min RTT {server['minDelayMs']} ms")
    # Only the nearest server is preferred; the others add operator diversity as fallbacks.
    lines += [f"server {server['host']} iburst{' prefer' if index == 0 else ''} minpoll 6 maxpoll 10"
              for index, server in enumerate(chosen)]
    return "\n".join(lines) + "\n"


def find_sourcedir(conf_paths=CHRONY_CONFS) -> str | None:
    """Return the first `sourcedir` directory declared in the Chrony configuration."""
    for path in conf_paths:
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    match = re.match(r"^\s*sourcedir\s+(\S+)", line)
                    if match:
                        return match.group(1)
        except OSError:
            continue
    return None


def _write_atomic(path: str, text: str) -> str | None:
    backup = None
    if os.path.exists(path):
        backup = f"{path}.bak"
        shutil.copy2(path, backup)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".roko-stratum1.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(temp, 0o644)
    os.replace(temp, path)
    return backup


def _chronyc(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["chronyc", *args], capture_output=True, text=True, timeout=30,
                          check=False, env=CHILD_ENV)


def install_sources(text: str, hosts: list[str], sourcedir: str | None) -> dict:
    if os.geteuid() != 0:
        raise InstallBlocked("installing Chrony sources needs root; re-run with sudo")
    if not sourcedir:
        raise InstallBlocked("Chrony has no 'sourcedir' directive; add 'sourcedir /etc/chrony/sources.d' "
                             "to chrony.conf (or paste the printed lines into it) and restart chrony")
    if shutil.which("chronyc") is None:
        raise InstallBlocked("chronyc not found; install chrony first")
    path = os.path.join(sourcedir, SOURCES_FILENAME)
    backup = _write_atomic(path, text)
    reload = _chronyc("reload", "sources")
    if reload.returncode != 0:
        raise InstallBlocked(f"wrote {path} but 'chronyc reload sources' failed: {reload.stderr.strip()[:200]}")
    listed = _chronyc("-c", "sources").stdout
    missing = [host for host in hosts if host not in listed]
    return {"path": path, "backup": backup, "missingAfterReload": missing}
