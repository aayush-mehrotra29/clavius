"""Source extraction and physical meaning of the independent wheel benchmark."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from planner.validation.mobility import POLICY, comparison, model_xml, simulate, traction_angle, wheel_omega
from scripts.prepare_mobility_reference import literal_arrays, sha

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / 'public/data/mobility-reference.json').read_text())


def test_hash_pinned_points_and_rig():
    manifest = json.loads((ROOT / 'public/data/mobility-reference-manifest.json').read_text())
    assert sha(ROOT / 'public/data/mobility-reference.json') == manifest['derivative']['sha256']
    assert [len(series['points']) for series in REFERENCE['series']] == [18, 6, 7]
    assert REFERENCE['series'][0]['points'][0]['slip_fraction'] < 0
    assert REFERENCE['series'][0]['points'][-1]['slip_fraction'] > .8
    assert REFERENCE['rig']['wheel_outer_radius_m'] == .25
    assert REFERENCE['rig']['normal_loaded_mass_kg'] == 17.5
    assert REFERENCE['role'] == 'validation_only'


def test_source_extraction_does_not_execute_python():
    text = 'raise RuntimeError("must not execute")\n' + '\n'.join(f'experimental{i} = numpy.array([0, {i}, 20, {i+1}])' for i in [1, 2, 3])
    result = literal_arrays(text)
    assert result['experimental3'] == [[0, 3], [20, 4]]


@pytest.mark.parametrize('bad', ['numpy.array([float("nan"), 1])', 'numpy.array([0, 1, 2])', '__import__("os").system("false")', 'numpy.array([0, 1], dtype=float)'])
def test_extraction_rejects_nonliteral_or_malformed_points(bad):
    text = f'experimental1 = {bad}\nexperimental2 = numpy.array([0, 1])\nexperimental3 = numpy.array([0, 1])'
    with pytest.raises((ValueError, TypeError)):
        literal_arrays(text)


def test_published_driving_slip_and_traction_conventions():
    assert wheel_omega(.2, .25, 0) == pytest.approx(.8)
    assert wheel_omega(.2, .25, .8) == pytest.approx(4.)
    assert traction_angle(100, 100) == pytest.approx(45.)
    assert traction_angle(-100, 100) == pytest.approx(-45.)
    with pytest.raises(ValueError):
        wheel_omega(.2, .25, 1.)
    with pytest.raises(ValueError):
        traction_angle(1, 0)


def test_source_geometry_and_free_vertical_load_path():
    root = ET.fromstring(model_xml(REFERENCE['rig'], .001, .7))
    grousers = [geom for geom in root.findall('.//geom') if geom.get('name', '').startswith('grouser_')]
    assert len(grousers) == 24
    body = root.find('.//body[@name="free_vertical_axle"]')
    assert body.find('joint').get('type') == 'slide'
    assert float(body.find('inertial').get('mass')) == 8.75
    assert float(body.find('body/inertial').get('mass')) == 8.75
    assert root.find('option').get('gravity') == '0 0 -9.81'


def test_native_benchmark_controls_load_and_finite_evidence():
    result, trace, _ = simulate(REFERENCE['rig'], .3, duration=10.1)
    assert result['controls_passed']
    assert result['mean_normal_force_n'] == pytest.approx(17.5*9.81, rel=.05)
    assert result['mean_actual_slip_fraction'] == pytest.approx(.3, abs=.002)
    assert result['mean_drawbar_pull_n'] > 0
    assert trace.shape[1] == 10
    assert result['mean_drawbar_pull_n'] == pytest.approx(result['mean_contact_longitudinal_n']-1.5*17.5*result['mean_horizontal_acceleration_m_s2'], abs=1e-10)
    assert np.isfinite(trace).all()
    json.dumps(result, allow_nan=False)


def test_numerical_success_does_not_mean_traction_or_lunar_accuracy():
    result = comparison([{'mean_traction_slope_deg': 40., 'published_traction_slope_deg': 5., 'controls_passed': True}])
    assert result['all_rig_controls_passed']
    assert not result['traction_development_targets_met']
    assert not result['lunar_validation_established']
    assert POLICY['calibration_fit_performed'] is False


def test_benchmark_cancellation_preserves_no_accepted_result():
    with pytest.raises(InterruptedError):
        simulate(REFERENCE['rig'], .1, cancel=lambda: True)
