"""Force-balance and evidence guards for the assembled-model component probe."""
import json

import numpy as np
import pytest

from scripts.benchmark_viper_rigid import COLUMNS,PROTOCOL,summarize


def fixture():
    policy=json.loads(PROTOCOL.read_text())
    trace=np.zeros(2001,dtype=[(name,'f8') for name in COLUMNS])
    trace['time_s']=np.linspace(0,20,2001);trace['vx_m_s']=.1
    trace['x_m']=trace['time_s']*.1;trace['z_m']=.25
    trace['normal_force_n']=policy['nominal_rig_mass_kg']*9.81
    trace['wheel_mean_omega_rad_s']=.4;trace['chassis_qw']=1
    return trace,policy


def test_component_force_balance_does_not_grant_flight_or_lunar_validation():
    trace,p=fixture();r=summarize(trace,9.81,.001,p)
    assert r['checks_passed']
    assert r['mean_normal_force_n']==pytest.approx(4266.5761273)
    assert r['mean_speed_m_s']==pytest.approx(.1)
    assert not r['flight_prediction_validated'] and not r['lunar_soil_validated']


def test_component_check_rejects_earth_weight_in_a_lunar_case():
    trace,p=fixture();r=summarize(trace,1.62,.001,p)
    assert not r['checks']['normal_load_balance']
    assert not r['checks_passed']


@pytest.mark.parametrize('mutation',['clock','nan','normalization'])
def test_incomplete_or_nonphysical_state_stays_rejected(mutation):
    trace,p=fixture()
    if mutation=='clock':
        with pytest.raises(ValueError):summarize(trace[:-1],9.81,.001,p)
    elif mutation=='nan':
        trace['vx_m_s'][100]=np.nan
        with pytest.raises(ValueError):summarize(trace,9.81,.001,p)
    else:
        trace['chassis_qw']=2
        assert not summarize(trace,9.81,.001,p)['checks_passed']
