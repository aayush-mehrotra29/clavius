"""Protocol separation and numerical evidence guards; native tests run separately."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest

from planner.validation import scm

COLUMNS=['time_s','x_m','z_m','vx_m_s','vz_m_s','omega_rad_s','terrain_force_x_n','terrain_force_z_n','terrain_torque_y_nm','linear_motor_force_n','spin_motor_torque_nm','center_sinkage_m','center_plastic_sinkage_m','ray_hits']


def analytical_trace():
    config=scm.configuration(.2)
    t=np.linspace(0,20,2001)
    rows=np.zeros(len(t),dtype=[(column,'f8') for column in COLUMNS])
    rows['time_s']=t;rows['x_m']=t*.2;rows['z_m']=.24
    rows['vx_m_s']=.2;rows['omega_rad_s']=1.
    rows['terrain_force_z_n']=17.5*9.81
    rows['terrain_force_x_n']=17.5*9.81*math.tan(math.radians(20))
    rows['center_sinkage_m']=.01;rows['center_plastic_sinkage_m']=.009;rows['ray_hits']=100
    return rows,config


def test_frozen_split_keeps_repeats_together():
    policy,points=scm.protocol()
    train=set(policy['training_source_indices']);holdout=set(policy['holdout_source_indices'])
    assert len(train)==10 and len(holdout)==8 and not train&holdout
    assert train|holdout==set(range(18))
    groups={}
    for point in points:
        # Nominal .05 is its own explicit group; nearby .1/.3 repeats stay together.
        group=round(point['slip_fraction']*20)
        groups.setdefault(group,set()).add('train' if point['source_index'] in train else 'holdout')
    assert all(len(values)==1 for values in groups.values())
    assert policy['maximum_parameter_candidates']==4
    assert policy['gravity_m_s2']==9.81


def test_analytical_steady_force_and_time_mean_are_in_si():
    rows,config=analytical_trace();result=scm.summarize(rows,config)
    assert result['controls_passed']
    assert result['mean_actual_slip_fraction']==pytest.approx(.2)
    assert result['mean_traction_slope_deg']==pytest.approx(20.)
    assert result['mean_center_plastic_sinkage_m']==pytest.approx(.009)
    assert result['reference_gravity_matches']
    assert not result['lunar_validation_established']
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('mutation',['nonfinite','truncated','unordered','wrong_columns','short_window'])
def test_incomplete_or_corrupt_native_evidence_is_rejected(mutation):
    rows,config=analytical_trace()
    if mutation=='nonfinite':rows['terrain_force_x_n'][100]=float('nan')
    elif mutation=='truncated':rows=rows[:-10]
    elif mutation=='unordered':rows['time_s'][50]=0
    elif mutation=='wrong_columns':rows=rows[['time_s','x_m']]
    else:config['duration_s']=9.;rows=rows[:901]
    with pytest.raises(ValueError):scm.summarize(rows,config)


def test_motion_or_load_failure_stays_failed():
    rows,config=analytical_trace();rows['vx_m_s']=.1;rows['terrain_force_z_n']=1
    result=scm.summarize(rows,config)
    assert not result['controls_passed']
    assert result['controls']['translation_tracking'] is False
    assert result['controls']['normal_load'] is False


def test_changed_gravity_does_not_inherit_earth_validation():
    rows,config=analytical_trace();config['gravity_m_s2']=1.62
    rows['terrain_force_z_n']=17.5*1.62
    result=scm.summarize(rows,config)
    assert result['controls_passed']
    assert not result['reference_gravity_matches']
    assert not result['lunar_validation_established']
