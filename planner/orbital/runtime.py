"""Verify the local GMAT runtime before each isolated native process."""
import hashlib
import json
import os
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOME = ROOT / 'data/runtime/gmat/sdk/R2026a'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verified_runtime(home=None):
    home = Path(home or os.environ.get('CLAVIUS_GMAT_HOME', str(DEFAULT_HOME))).resolve()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('This reference runtime is verified for Apple Silicon macOS only')
    record = json.loads((home / 'clavius-runtime.json').read_text())
    if record['version'] != 'R2026a' or record['profile'] != 'clavius-gmat-macos-universal-v1':
        raise ValueError('Unsupported GMAT runtime identity')
    pin = json.loads((ROOT / 'planner/orbital/references/distribution-manifest.json').read_text())
    if record['distribution'] != pin:
        raise ValueError('GMAT distribution differs from the pinned release')
    for item in record['files']:
        file = home / item['file']
        if not file.resolve().is_relative_to(home) or file.is_symlink() or file.stat().st_size != item['installed_bytes'] or digest(file) != item['sha256'] or item['sha256'] != item['source_sha256']:
            raise ValueError('GMAT runtime file differs: ' + item['file'])
    for alias in record['symlinks']:
        file = home / alias['file']
        if not file.is_symlink() or os.readlink(file) != alias['target'] or not file.resolve().is_relative_to(home):
            raise ValueError('GMAT runtime alias differs: ' + alias['file'])
    original = next(item for item in record['files'] if item['file'] == 'bin/gmat_startup_file.txt')
    if digest(home / 'original-gmat-startup.txt') != original['source_sha256']:
        raise ValueError('Original GMAT startup specification differs')
    content = {'version': record['version'], 'profile': record['profile'], 'distribution_sha256': pin['sha256'], 'files': [{'file': item['file'], 'sha256': item['sha256']} for item in record['files']], 'symlinks': record['symlinks']}
    identity = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return home, record, identity


def verified_reference(case):
    from .cases import CASES, REFERENCES
    spec = CASES[case]
    manifest = json.loads((REFERENCES / 'manifest.json').read_text())
    pin = next(item for item in manifest['scripts'] if item['file'] == spec['file'])
    file = REFERENCES / pin['file']
    if file.stat().st_size != pin['bytes'] or digest(file) != pin['sha256']:
        raise ValueError('Canonical GMAT reference script differs')
    return file, pin


def prepare_startup(home, output):
    from scripts.install_gmat_macos import startup_text
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    text, disabled = startup_text((home / 'original-gmat-startup.txt').read_text(), home, output)
    path = output / 'gmat_startup_file.txt'
    path.write_text(text)
    return path, disabled
