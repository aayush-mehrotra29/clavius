"""Verified runtime and independent scoring for the VIPER frame correction."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from planner.validation.scm import ROOT, digest, verified_runtime as original_runtime

PROTOCOL = ROOT / 'planner/validation/viper_frame_protocol.json'
INVENTORY = ROOT / 'data/runtime/viper-adapted-runtime.json'


def verified_runtime():
    _, baseline = original_runtime()
    record = json.loads(INVENTORY.read_text())
    if record['reference_runtime_identity'] != baseline['runtime_identity']:
        raise ValueError('The adapted model uses a different baseline runtime')
    expected_executables = {name: 'data/runtime/viper-adapted-build/' + filename for name, filename in [
        ('frames_original', 'clavius_viper_frames_original'),
        ('frames_repaired', 'clavius_viper_frames_repaired'),
        ('rigid_repaired', 'clavius_viper_rigid_repaired'),
    ]}
    if record['executables'] != expected_executables:
        raise ValueError('Adapted runtime executable bindings differ')
    for item in record['files']:
        file = ROOT / item['file']
        if not file.resolve().is_relative_to(ROOT) or digest(file) != item['sha256']:
            raise ValueError('Adapted runtime differs: ' + item['file'])
    fields = ['id', 'upstream_commit', 'reference_runtime_identity', 'files', 'compiler', 'configuration']
    identity = hashlib.sha256(json.dumps({key: record[key] for key in fields}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if identity != record['runtime_identity']:
        raise ValueError('Adapted runtime inventory identity differs')
    return record


def score_frame(raw, policy):
    names = ['wheel_LF_body', 'wheel_RF_body', 'wheel_LB_body', 'wheel_RB_body']
    if [wheel['name'] for wheel in raw['wheels']] != names:
        raise ValueError('Frame evidence must contain the original four wheels')
    if raw['mode'] not in ['static', 'torque', 'wrong-axis'] or raw['pose'] not in policy['poses']:
        raise ValueError('Unsupported frame case')
    if raw['variant'] not in ['upstream-original', 'clavius-frame-repaired'] or raw['flight_or_soil_validation'] is not False:
        raise ValueError('Unsupported model or validation claim')
    expected_time = 0 if raw['mode'] == 'static' else policy['torque_case']['duration_s']
    if not np.isfinite(raw['native_time_s']) or abs(raw['native_time_s'] - expected_time) > 1e-9:
        raise ValueError('Incomplete native component clock')
    metrics = {key: [] for key in ['cog', 'tensor', 'axis', 'wheel_mass', 'forward_speed']}
    for wheel in raw['wheels']:
        cog = np.asarray(wheel['body_cog_reference_m'], dtype=float)
        reference_cog = np.asarray(wheel['collider_cog_reference_m'], dtype=float)
        actual = np.asarray(wheel['body_inertia_reference_kg_m2'], dtype=float)
        expected = np.asarray(wheel['collider_inertia_reference_kg_m2'], dtype=float)
        axis = np.asarray(wheel['shaft_axis_reference'], dtype=float)
        omega = np.asarray(wheel['wheel_omega_reference_rad_s'], dtype=float)
        if cog.shape != (3,) or reference_cog.shape != (3,) or actual.shape != (3, 3) or expected.shape != (3, 3) or axis.shape != (3,) or omega.shape != (3,):
            raise ValueError('Invalid native frame/tensor dimensions')
        arrays = [cog, reference_cog, actual, expected, axis, omega]
        if any(not np.isfinite(value).all() for value in arrays):
            raise ValueError('Nonfinite native frame evidence')
        if not np.isfinite(wheel['shaft_omega_rad_s']):
            raise ValueError('Nonfinite native shaft telemetry')
        if np.linalg.eigvalsh(actual).min() <= 0 or np.linalg.eigvalsh(expected).min() <= 0:
            raise ValueError('Nonphysical inertia tensor')
        if abs(np.linalg.norm(axis) - 1) > 1e-8:
            raise ValueError('Invalid native shaft unit direction')
        values = {
            'cog': float(np.linalg.norm(cog - reference_cog)),
            'tensor': float(np.linalg.norm(actual - expected) / np.linalg.norm(expected)),
            'axis': float(np.linalg.norm(axis - np.array([0., -1., 0.]))),
            'wheel_mass': abs(wheel['mass_kg'] - wheel['collider_mass_kg']),
            'forward_speed': float(omega[1]),
        }
        for key, stored in [('cog', 'cog_difference_m'), ('tensor', 'relative_tensor_difference'), ('axis', 'shaft_axis_difference')]:
            if not np.isclose(values[key], wheel[stored], rtol=1e-10, atol=1e-14):
                raise ValueError('Stored native frame metric differs: ' + stored)
        for key, value in values.items():
            if not np.isfinite(value):
                raise ValueError('Nonfinite native frame metric')
            metrics[key].append(value)
    scalars = [raw[key] for key in ['all_body_mass_kg', 'reported_rover_mass_kg', 'maximum_joint_constraint_residual', 'maximum_shaft_speed_relation_error_rad_s']]
    if not np.isfinite(scalars).all() or min(scalars[:2]) <= 0 or min(scalars[2:]) < 0:
        raise ValueError('Invalid native model mass or residual')
    limits = policy['checks']
    checks = {
        'collider_cog_frames': max(metrics['cog']) <= limits['maximum_cog_difference_m'],
        'collider_inertia_tensors': max(metrics['tensor']) <= limits['maximum_relative_tensor_difference'],
        'shaft_reference_directions': max(metrics['axis']) <= limits['maximum_shaft_axis_difference'],
        'wheel_mass_preserved': max(metrics['wheel_mass']) <= limits['maximum_mass_accounting_error_kg'],
        'total_mass_accounting': abs(raw['all_body_mass_kg'] - raw['reported_rover_mass_kg']) <= limits['maximum_mass_accounting_error_kg'],
        'joint_constraints': raw['maximum_joint_constraint_residual'] <= limits['maximum_joint_constraint_residual'],
        'shaft_speed_relation': raw['maximum_shaft_speed_relation_error_rad_s'] <= limits['maximum_shaft_speed_relation_error_rad_s'],
        'forward_torque_response': None if raw['mode'] == 'static' else min(metrics['forward_speed']) >= limits['minimum_forward_wheel_speed_rad_s'],
    }
    return {'variant': raw['variant'], 'mode': raw['mode'], 'pose': raw['pose'], 'checks': checks, 'checks_passed': all(value for value in checks.values() if value is not None), 'maximum_cog_difference_m': max(metrics['cog']), 'maximum_relative_tensor_difference': max(metrics['tensor']), 'maximum_shaft_axis_difference': max(metrics['axis']), 'mass_accounting_error_kg': raw['reported_rover_mass_kg'] - raw['all_body_mass_kg'], 'forward_wheel_speeds_rad_s': metrics['forward_speed'], 'flight_prediction_validated': False, 'lunar_soil_validated': False}


def execute(executable, arguments, directory, runtime, timeout=900, cancel=lambda: False):
    """Record launches before execution; retain terminal/cancelled evidence."""
    verified_runtime()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    command = [str(executable), *map(str, arguments)]
    invocation = {'started_utc': datetime.now(timezone.utc).isoformat(), 'command': command, 'runtime_identity': runtime['runtime_identity'], 'executable_sha256': digest(executable), 'protocol_sha256': digest(PROTOCOL), 'wall_limit_s': timeout, 'state': 'running'}
    inv_file = directory / 'invocation.json'
    inv_file.write_text(json.dumps(invocation, indent=2) + '\n')
    started = time.monotonic()
    process = None
    error = None
    with (directory / 'native.log').open('w') as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
            while process.poll() is None:
                cancelled = cancel()
                if cancelled or time.monotonic() - started > timeout:
                    invocation['state'] = 'cancelled' if cancelled else 'timed_out'
                    break
                try:
                    process.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException as exc:
            invocation['state'] = 'interrupted'
            error = exc
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            invocation.update(returncode=process.returncode if process else None, elapsed_wall_s=time.monotonic() - started)
            if invocation['state'] == 'running':
                invocation['state'] = 'completed' if invocation['returncode'] == 0 else 'failed'
            inv_file.write_text(json.dumps(invocation, indent=2) + '\n')
    if error is not None:
        raise error
    if invocation['state'] != 'completed':
        raise RuntimeError('Native adapted-model case ' + invocation['state'] + '; evidence retained at ' + str(directory))
    return invocation
