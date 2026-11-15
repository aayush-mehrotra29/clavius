"""Recorded native reference evidence plus deliberate malformed/failure cases."""
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import subprocess

import pytest

from planner.orbital.cases import CASES
from planner.orbital.references import run_process
from planner.orbital.validation import EvidenceError, endpoint_checks, osculating, solver_log, summary_state, utc_iso

FIXTURES = Path(__file__).parent / 'fixtures/gmat'


def fixture(case='fixed-epoch'):
    root = FIXTURES / case
    record = json.loads((root / 'fixture.json').read_text())
    states = {}
    for role, item in record['state_files'].items():
        frame = record['native']['frames'][item['frame']]
        states[role + ('_earth' if role == 'departure' else '_moon')] = summary_state((root / item['file']).read_text(), CASES[case]['spacecraft'], item['frame'], frame['Origin'], frame['Axes'])
    return record, states


@pytest.mark.parametrize('case,counts', [('fixed-epoch', [37, 7]), ('lunar-transfer', [6, 4])])
def test_native_reference_residuals_and_iterations(case, counts):
    result = solver_log((FIXTURES / case / 'console.log').read_text(), CASES[case]['targets'])
    assert result['passed']
    assert [len(loop['iterations']) for loop in result['loops']] == counts
    # Names are actual expressions. The second source swaps two human labels.
    if case == 'lunar-transfer':
        first = result['loops'][0]['iterations'][-1]['goals'][0]
        assert first['name'].endswith('.BdotT')
        assert first['achieved'] == pytest.approx(14998.6063605)


@pytest.mark.parametrize('marker', ['*** The Targeter converged!', 'Mission run completed.', '*** Targeting Completed in 7 iterations.'])
def test_exit_success_without_required_native_markers_is_insufficient(marker):
    text = (FIXTURES / 'fixed-epoch/console.log').read_text().replace(marker, '', 1)
    assert not solver_log(text, CASES['fixed-epoch']['targets'])['passed']


@pytest.mark.parametrize('mutation', ['missing_goal', 'wrong_expression', 'nonfinite', 'inconsistent_variance', 'missing_iteration', 'extra_loop'])
def test_corrupted_solver_evidence_is_rejected(mutation):
    text = (FIXTURES / 'fixed-epoch/console.log').read_text()
    if mutation == 'missing_goal':
        text = re.sub(r'^\s+MoonSat.EarthMoonRot.RA  Desired:.*\n', '', text, count=1, flags=re.MULTILINE)
    elif mutation == 'wrong_expression':
        text = text.replace('MoonSat.EarthMoonRot.RA  Desired:', 'MoonSat.Luna.RMAG  Desired:', 1)
    elif mutation == 'nonfinite':
        text = text.replace('Achieved: -152.533210209', 'Achieved: nan', 1)
    elif mutation == 'inconsistent_variance':
        text = text.replace('Variance: 152.533210209', 'Variance: 0', 1)
    elif mutation == 'missing_iteration':
        text = text.replace('DC1 Iteration 2; Nominal Pass', 'DC1 Iteration 3; Nominal Pass', 1)
    else:
        text += '\n*** Performing Differential Correction (using "DC1")'
    with pytest.raises(EvidenceError):
        solver_log(text, CASES['fixed-epoch']['targets'])


def test_convergence_marker_does_not_override_failed_residual():
    text = (FIXTURES / 'fixed-epoch/console.log').read_text()
    text = text.replace('Achieved: 15000.0003921  Variance: -0.000392089139496', 'Achieved: 15001  Variance: -1')
    assert not solver_log(text, CASES['fixed-epoch']['targets'])['passed']


@pytest.mark.parametrize('case', list(CASES))
def test_native_endpoints_and_frames(case):
    record, states = fixture(case)
    native, spec = record['native'], CASES[case]
    result = endpoint_checks(states, native['bodies'], native['burns'], spec['encounter_guards'], spec['post_capture_days'])
    assert result['passed']
    assert result['native_moon_radius_m'] == 1738200
    assert result['policy']['full_trajectory_clearance_checked'] is False
    assert result['policy']['tighter_repropagation_checked'] is False
    assert states['departure_earth']['frame_id'] == 'EarthMJ2000Eq'
    assert states['capture_moon']['frame_id'] == spec['moon_frame']
    assert states['capture_moon']['axes'] == ('BodyInertial' if case == 'fixed-epoch' else 'MJ2000Eq')
    assert result['post_capture_duration_s'] == pytest.approx(spec['post_capture_days']*86400, abs=.01)
    if case == 'fixed-epoch':
        assert states['capture_moon']['position_m'][0] == pytest.approx(-3286325.6567048)
        assert states['capture_moon']['epoch_utc'] == '2022-07-19T15:17:22.067Z'


@pytest.mark.parametrize('mutation', ['wrong_frame', 'wrong_units', 'nonfinite', 'duplicate_state', 'wrong_spacecraft'])
def test_summary_requires_frame_units_and_exact_intended_state(mutation):
    record = json.loads((FIXTURES / 'fixed-epoch/fixture.json').read_text())
    item = record['state_files']['capture']
    text = (FIXTURES / 'fixed-epoch' / item['file']).read_text()
    if mutation == 'wrong_frame':
        text = text.replace('Coordinate System: MoonInertial', 'Coordinate System: EarthMJ2000Eq')
    elif mutation == 'wrong_units':
        text = re.sub(r'(X\s*=\s*\S+) km', r'\1 m', text)
    elif mutation == 'nonfinite':
        text = re.sub(r'(X\s*=\s*)\S+', r'\1inf', text)
    elif mutation == 'duplicate_state':
        text += text
    else:
        text = text.replace('MoonSat', 'OtherSat')
    with pytest.raises(EvidenceError):
        summary_state(text, 'MoonSat', 'MoonInertial', 'Luna', 'BodyInertial')


def test_rotating_report_frame_is_not_inertial_state():
    with pytest.raises(EvidenceError):
        summary_state('', 'MoonSat', 'MOON_ME_DE421', 'Luna', 'BodyFixed')


def test_utc_leap_second_is_preserved():
    assert utc_iso('31 Dec 2016 23:59:60.500') == '2016-12-31T23:59:60.500Z'


def test_two_body_circular_state_in_si_units():
    mu, radius = 4902.8005821478e9, 2e6
    result = osculating({'position_m': [radius, 0., 0.], 'velocity_m_s': [0., math.sqrt(mu/radius), 0.]}, mu)
    assert result['specific_energy_m2_s2'] == pytest.approx(-mu/(2*radius))
    assert result['eccentricity'] == pytest.approx(0., abs=1e-15)
    assert result['osculating_periapsis_radius_m'] == pytest.approx(radius)


@pytest.mark.parametrize('mutation,failed', [('time_guard', 'encounter_before_time_guard'), ('radius_guard', 'encounter_above_radius_guard'), ('unbound', 'capture_moon_negative_energy'), ('body_intersection', 'capture_moon_outside_lunar_sphere'), ('mismatched_impulse', 'insertion_impulse_matches')])
def test_physical_failure_is_not_accepted(mutation, failed):
    record, states = fixture()
    native, spec = deepcopy(record['native']), CASES['fixed-epoch']
    if mutation == 'time_guard':
        states['encounter_moon']['epoch_tai_gmat_mod_julian'] = states['departure_earth']['epoch_tai_gmat_mod_julian'] + 6
    elif mutation == 'radius_guard':
        states['encounter_moon']['position_m'] = [1e6, 0., 0.]
    elif mutation == 'unbound':
        states['capture_moon']['velocity_m_s'] = [1e4, 0., 0.]
    elif mutation == 'body_intersection':
        states['capture_moon']['position_m'] = [1e6, 0., 0.]
    else:
        native['burns']['LOI']['Element1'] = '-.5'
    result = endpoint_checks(states, native['bodies'], native['burns'], spec['encounter_guards'], spec['post_capture_days'])
    assert result['checks'][failed] is False
    assert result['passed'] is False


def test_wrong_central_body_is_rejected():
    record, states = fixture()
    states['capture_moon']['origin'] = 'Earth'
    with pytest.raises(EvidenceError):
        endpoint_checks(states, record['native']['bodies'], record['native']['burns'], {}, 4)


def test_worker_timeout_is_preserved(monkeypatch, tmp_path):
    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', expired)
    result = run_process(['trusted-worker'], tmp_path, tmp_path / 'native.log', timeout=1)
    assert result['timed_out'] is True
    assert result['returncode'] is None
