"""Run and check both original NASA cases through Console and Python API.

This is a reference benchmark, not an accepted departure-search candidate. Run
with: .venv/bin/python -m planner.orbital.references --output <fresh-directory>
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from .cases import CASES
from .runtime import ROOT, digest, prepare_startup, verified_reference, verified_runtime
from .validation import EvidenceError, endpoint_checks, solver_log, summary_state


def state_for(output, commands, command, spec, native, frame):
    descriptor = next(item for item in commands if item['index'] == command)
    item = descriptor['summaries'][frame]
    file = output / item['file']
    if not file.resolve().is_relative_to(output) or digest(file) != item['sha256']:
        raise EvidenceError('Changed or escaping native summary')
    metadata = native['frames'][frame]
    return summary_state(file.read_text(), spec['spacecraft'], frame, metadata['Origin'], metadata['Axes'])


def validate_case(case, console, api, identity):
    spec = CASES[case]
    _, pin = verified_reference(case)
    console_run = json.loads((console / 'invocation.json').read_text())
    api_run = json.loads((api / 'process.json').read_text())
    native = json.loads((api / 'native-result.json').read_text())
    if console_run['returncode'] != 0 or api_run['returncode'] != 0 or not native['load_succeeded'] or not native['run_succeeded']:
        raise EvidenceError('Native process failed')
    if native['runtime_identity'] != identity or console_run['runtime_identity'] != identity or native['script'] != pin or console_run['script'] != pin:
        raise EvidenceError('Wrong runtime or source identity')
    text_logs = {'console': (console / 'console.log').read_text(), 'api': (api / 'api-native.log').read_text()}
    for text in text_logs.values():
        import re
        if set(re.findall(r'Successfully set Planetary Source to use: (\S+)', text)) != {'DE405'}:
            raise EvidenceError('Native ephemeris identity differs from the reference')
    logs = {name: solver_log(text, spec['targets']) for name, text in text_logs.items()}
    goals_agree = all(math.isclose(cg['achieved'], ag['achieved'], abs_tol=max(1e-8, cg['tolerance']*1e-6), rel_tol=0) for cl, al in zip(logs['console']['loops'], logs['api']['loops']) for cg, ag in zip(cl['iterations'][-1]['goals'], al['iterations'][-1]['goals']))
    commands = json.loads((api / 'commands.json').read_text())
    selected = {}
    for role, (kind, name) in spec['physical_command_names'].items():
        matches = [item for item in commands if item['type'] == kind and item['name'] == name]
        if 'physical_commands' in spec:
            matches = [item for item in matches if item['index'] == spec['physical_commands'][role]]
        if len(matches) != 1:
            raise EvidenceError('Missing or ambiguous physical command: ' + role)
        selected[role] = matches[0]['index']
    states = {role + ('_earth' if role == 'departure' else '_moon'): state_for(api, commands, command, spec, native, 'EarthMJ2000Eq' if role == 'departure' else spec['moon_frame']) for role, command in selected.items()}
    endpoints = endpoint_checks(states, native['bodies'], native['burns'], spec['encounter_guards'], spec['post_capture_days'])
    initialization = None
    if spec.get('coarse_initialization_commands'):
        departure, arrival = [state_for(api, commands, command, spec, native, 'EarthMJ2000Eq') for command in spec['coarse_initialization_commands']]
        elapsed = (arrival['epoch_tai_gmat_mod_julian']-departure['epoch_tai_gmat_mod_julian'])*86400
        initialization = {'role': 'Procedural coarse initialization only; MoonSat is reset from InitSat before the fine solve. Excluded from physical transfer and delta-v.', 'duration_s': elapsed, 'time_guard_reached': abs(elapsed-4.5*86400) < .01}
    passed = goals_agree and endpoints['passed'] and all(log['passed'] for log in logs.values())
    return {'case': case, 'reference_checks_passed': passed, 'screening_candidate_accepted': False, 'source': pin, 'runtime_identity': identity, 'native': native, 'solver_evidence': logs, 'console_api_goals_agree': goals_agree, 'selected_commands': selected, 'states': states, 'endpoint_checks': endpoints, 'initialization': initialization,
            'limitations': ['Reference benchmark only. Full trajectory Earth/Moon clearance and tighter independent repropagation are not yet checked.', 'The original solver tolerances are retained; the fixed-epoch eccentricity tolerance is 0.1.', 'Impulsive burns do not decrement mass. Launch, propellant and vehicle compatibility are unassessed.', 'No descent or landing-site access is solved. Surface DE421 geometry and its 1737.4 km sphere are distinct from this native GMAT DE405 model and 1738.2 km lunar radius.']}


def run_process(command, cwd, log, timeout):
    started = time.monotonic()
    with log.open('w') as stream:
        try:
            process = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            return {'returncode': process.returncode, 'timed_out': False, 'elapsed_s': time.monotonic()-started, 'command': command}
        except subprocess.TimeoutExpired:
            return {'returncode': None, 'timed_out': True, 'elapsed_s': time.monotonic()-started, 'command': command}


def run(output, timeout=120):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    home, runtime, identity = verified_runtime()
    (output / 'runtime-inventory.json').write_text(json.dumps(runtime, indent=2) + '\n')
    cases, failures = [], []
    for case in CASES:
        console, api = output / case / 'console', output / case / 'api'
        console.mkdir(parents=True)
        startup, disabled = prepare_startup(home, console)
        script, pin = verified_reference(case)
        command = [str(home / 'bin/GmatConsole'), '-s', str(startup), '-r', str(script), '-l', str(console / 'GmatLog.txt')]
        console_record = run_process(command, home / 'bin', console / 'console.log', timeout)
        console_record.update(runtime_identity=identity, script=pin, disabled_optional_plugins=disabled, startup_sha256=digest(startup))
        (console / 'invocation.json').write_text(json.dumps(console_record, indent=2) + '\n')
        command = [sys.executable, '-m', 'planner.orbital.native_worker', '--case', case, '--output', str(api)]
        api_record = run_process(command, ROOT, output / case / 'api-process.log', timeout)
        api.mkdir(exist_ok=True)
        (api / 'process.json').write_text(json.dumps(api_record, indent=2) + '\n')
        try:
            result = validate_case(case, console, api, identity)
            cases.append(result)
        except (EvidenceError, OSError, KeyError, ValueError) as error:
            failures.append({'case': case, 'type': type(error).__name__, 'message': str(error)})
    # Include exact source and adapter bytes in the evidence, separate from data.
    sources = output / 'sources'
    sources.mkdir()
    source_paths = [*sorted((ROOT / 'planner/orbital').glob('*.py')), ROOT / 'scripts/install_gmat_macos.py', *sorted((ROOT / 'planner/orbital/references').glob('*'))]
    for file in source_paths:
        if file.is_file():
            relative = file.relative_to(ROOT)
            target = sources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
    shutil.copyfile(home / 'License.txt', sources / 'NASA-GMAT-License.txt')
    files = [{'file': str(file.relative_to(output)), 'sha256': digest(file), 'bytes': file.stat().st_size} for file in sorted(output.rglob('*')) if file.is_file()]
    report = {'model_id': 'clavius-gmat-reference-benchmark-v1', 'created_utc': datetime.now(timezone.utc).isoformat(), 'runtime_identity': identity, 'distribution': runtime['distribution'], 'native_ephemeris': 'DE405', 'native_build': 'Mar 26 2026 19:40:07', 'passed': len(cases) == len(CASES) and not failures and all(case['reference_checks_passed'] for case in cases), 'cases': cases, 'failures': failures, 'evidence_files': files}
    (output / 'benchmark.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    with zipfile.ZipFile(output.with_suffix('.zip'), 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(output.rglob('*')):
            if file.is_file():
                archive.write(file, file.relative_to(output))
    print(json.dumps({'passed': report['passed'], 'report': str(output / 'benchmark.json'), 'archive': str(output.with_suffix('.zip')), 'failures': failures}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output)['passed'] else 1)


if __name__ == '__main__':
    main()
