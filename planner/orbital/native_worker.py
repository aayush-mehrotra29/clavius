"""One isolated GMAT API process, restricted to the pinned NASA reference cases.

stdout/stderr are captured by the parent. Native command summaries are extracted
after execution; setting their report frame/name does not alter propagation.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

from .cases import CASES
from .runtime import digest, prepare_startup, verified_reference, verified_runtime


def fields(obj, names):
    return {name: obj.GetField(name) for name in names}


def execute(case, output):
    started = time.monotonic()
    home, runtime, identity = verified_runtime()
    script, pin = verified_reference(case)
    spec = CASES[case]
    startup, disabled = prepare_startup(home, output)
    record = {
        'case': case, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'runtime_identity': identity, 'version': runtime['version'],
        'distribution_sha256': runtime['distribution']['sha256'],
        'script': pin, 'script_unchanged': True,
        'startup_sha256': digest(startup), 'disabled_optional_plugins': disabled,
        'python': platform.python_version(), 'machine': platform.machine(),
        'load_succeeded': False, 'run_succeeded': False,
    }
    (output / 'invocation.json').write_text(json.dumps(record, indent=2) + '\n')
    # The sample's CSSI support path is relative to the original bin directory.
    os.chdir(home / 'bin')
    sys.path.insert(0, str(home / 'bin'))
    import gmatpy as gmat
    gmat.Setup(str(startup))  # Native Setup returns None on success.
    gmat.UseLogFile(str(output / 'api-native.log'))
    record['load_succeeded'] = bool(gmat.LoadScript(str(script)))
    if not record['load_succeeded']:
        raise RuntimeError('GMAT did not load the pinned script')
    record['initial_spacecraft'] = fields(gmat.GetObject(spec['spacecraft']), ['DateFormat', 'Epoch', 'CoordinateSystem', 'DisplayStateType', 'X', 'Y', 'Z', 'VX', 'VY', 'VZ', 'DryMass'])
    record['frames'] = {frame: fields(gmat.GetObject(frame), ['Origin', 'Axes']) for frame in ['EarthMJ2000Eq', spec['moon_frame']]}
    record['run_succeeded'] = bool(gmat.RunScript())
    if not record['run_succeeded']:
        raise RuntimeError('GMAT native run failed')
    record['bodies'] = {body: fields(gmat.GetObject(body), ['Mu', 'EquatorialRadius', 'Flattening']) for body in ['Earth', 'Luna']}
    record['burns'] = {name: fields(gmat.GetRuntimeObject(name), ['CoordinateSystem', 'Origin', 'Axes', 'Element1', 'Element2', 'Element3', 'DecrementMass']) for name in ['TOI', 'LOI']}
    record['solver'] = fields(gmat.GetRuntimeObject('DC1'), ['MaximumIterations', 'DerivativeMethod', 'Algorithm'])
    record['final_spacecraft'] = fields(gmat.GetRuntimeObject(spec['spacecraft']), ['DateFormat', 'Epoch', 'CoordinateSystem', 'X', 'Y', 'Z', 'VX', 'VY', 'VZ', 'DryMass'])
    commands = []
    for index, cmd in enumerate(gmat.GetCommands()):
        item = {'index': index, 'type': cmd.GetTypeName(), 'name': cmd.GetName(), 'source': cmd.GetGeneratingString()}
        if item['type'] in ['Maneuver', 'Propagate', 'GMAT']:
            item['summaries'] = {}
            cmd.SetSummaryName('CLAVIUS_CMD_%03d' % index)
            for frame in record['frames']:
                cmd.SetupSummary(frame, False, False)
                summary = cmd.GetStringParameter('Summary')
                filename = '%03d-%s.txt' % (index, frame)
                (output / filename).write_text(summary)
                item['summaries'][frame] = {'file': filename, 'sha256': digest(output / filename)}
        commands.append(item)
    (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    summary = io.StringIO()
    with contextlib.redirect_stdout(summary):
        returned = gmat.GetRunSummary()
    (output / 'mission-summary.txt').write_text(returned if isinstance(returned, str) else summary.getvalue())
    if digest(script) != pin['sha256']:
        raise ValueError('Reference script changed during execution')
    record['elapsed_s'] = time.monotonic() - started
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (output / 'native-result.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    # Caller must allocate a fresh directory. Never overwrite earlier evidence.
    output.mkdir(parents=True, exist_ok=False)
    try:
        execute(args.case, output)
    except BaseException as error:
        (output / 'failure.json').write_text(json.dumps({'type': type(error).__name__, 'message': str(error)}, indent=2) + '\n')
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == '__main__':
    main()
