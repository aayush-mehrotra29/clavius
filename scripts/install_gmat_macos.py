"""Install and inventory the complete pinned official macOS GMAT distribution.

Every distributed file retains its original bytes, including universal binaries
and the original startup file. Per-job startup files relocate paths and outputs;
they do not change reference missions or numerical input files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'data/runtime/gmat/sdk/R2026a'
PROFILE = 'clavius-gmat-macos-universal-v1'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def startup_text(original, sdk, output):
    lines, disabled = [], []
    for line in original.splitlines():
        match = re.match(r'\s*([A-Z_]+)\s*=\s*(.*?)\s*$', line)
        if not match:
            lines.append(line)
            continue
        key, value = match.groups()
        if key == 'PLUGIN':
            if 'proprietary/' in value or any(name in value for name in ['libMatlabInterface', 'libPythonInterface', 'libExternalForceModel']):
                disabled.append(value)
                lines.append('# CLAVIUS_UNUSED_OPTIONAL_PLUGIN ' + line)
                continue
            value = str((sdk / 'bin' / value).absolute())
        elif key == 'ROOT_PATH':
            value = str(sdk) + '/'
        elif key == 'OUTPUT_PATH':
            value = str(output) + '/'
        elif key == 'FILE_UPDATE_PATH':
            value = str(sdk / 'disabled-updates') + '/'
        lines.append(key + ' = ' + value)
    lines.extend(['MATLAB_MODE = NO_MATLAB', 'RUN_MODE = TESTING_NO_PLOTS'])
    return '\n'.join(lines) + '\n', disabled


def install(sdk, dry_run=False):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('This installer is verified for Apple Silicon macOS')
    if DESTINATION.exists():
        raise ValueError('Destination exists; verify it instead of overwriting')
    pin = json.loads((ROOT / 'planner/orbital/references/distribution-manifest.json').read_text())
    distribution = json.loads((ROOT / 'data/runtime/gmat/distribution.json').read_text())
    image = Path(distribution['file'])
    if image.stat().st_size != pin['bytes'] or digest(image) != pin['sha256']:
        raise ValueError('Original DMG differs from pinned distribution')
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(sdk / 'bin/GmatConsole')], check=True)
    files, aliases = [], []
    for source in sorted(sdk.rglob('*')):
        relative = str(source.relative_to(sdk))
        if source.is_symlink():
            if not source.resolve().is_relative_to(sdk):
                raise ValueError('Escaping source symlink: ' + relative)
            aliases.append({'file': relative, 'target': os.readlink(source)})
        elif source.is_file():
            files.append({'file': relative, 'installed_bytes': source.stat().st_size, 'source_sha256': digest(source)})
    required = sum(item['installed_bytes'] for item in files)
    free = shutil.disk_usage(ROOT).free
    print(json.dumps({'files': len(files), 'logical_bytes': required, 'available_bytes': free, 'dry_run': dry_run}), flush=True)
    if dry_run:
        return
    if free < required + 256 * 1024**2:
        raise ValueError('Insufficient space for complete transactional install')
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.gmat-complete-install-', dir=DESTINATION.parent))
    try:
        subprocess.run(['/usr/bin/ditto', '--hfsCompression', str(sdk), str(staging)], check=True)
        for item in files:
            target = staging / item['file']
            if target.stat().st_size != item['installed_bytes'] or digest(target) != item['source_sha256']:
                raise ValueError('Installed bytes differ: ' + item['file'])
            item['sha256'] = item['source_sha256']
            if item['file'].startswith('data/'):
                target.chmod(target.stat().st_mode & ~0o222)
        for alias in aliases:
            target = staging / alias['file']
            if not target.is_symlink() or os.readlink(target) != alias['target'] or not target.resolve().is_relative_to(staging):
                raise ValueError('Installed symlink differs: ' + alias['file'])
        subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(staging / 'bin/GmatConsole')], check=True)
        shutil.copyfile(staging / 'bin/gmat_startup_file.txt', staging / 'original-gmat-startup.txt')
        for name in ['output', 'disabled-updates']:
            (staging / name).mkdir(exist_ok=True)
        record = {
            'software': 'NASA GMAT', 'version': 'R2026a', 'profile': PROFILE,
            'distribution': pin, 'files': files, 'symlinks': aliases,
            'startup_policy': 'Original startup retained byte-for-byte. Private job startup relocates paths/output, disables updates and unused external SDK plugins, and suppresses plots. No numerical data or mission edits.',
            'scope': 'Complete official universal macOS distribution; all original files and native signatures retained.'}
        (staging / 'clavius-runtime.json').write_text(json.dumps(record, indent=2) + '\n')
        staging.rename(DESTINATION)
        print('Installed ' + str(DESTINATION), flush=True)
    except BaseException:
        shutil.rmtree(staging)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    install(args.source.resolve(), args.dry_run)


if __name__ == '__main__':
    main()
