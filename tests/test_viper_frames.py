"""Guard native frame evidence without treating model consistency as flight data."""
import json

import numpy as np
import pytest

from planner.validation.viper_frames import PROTOCOL, score_frame


def analytical_frames(mode='torque'):
    wheels=[]
    for name in ['wheel_LF_body','wheel_RF_body','wheel_LB_body','wheel_RB_body']:
        wheels.append({'name':name,'mass_kg':11.,'collider_mass_kg':11.,'body_cog_reference_m':[0.,0.,0.], 'collider_cog_reference_m':[0.,0.,0.], 'body_inertia_reference_kg_m2':np.diag([.2,.3,.4]).tolist(), 'collider_inertia_reference_kg_m2':np.diag([.2,.3,.4]).tolist(), 'cog_difference_m':0., 'relative_tensor_difference':0., 'shaft_axis_reference':[0.,-1.,0.], 'shaft_axis_difference':0., 'wheel_omega_reference_rad_s':[0.,.3,0.], 'shaft_omega_rad_s':-.3})
    return {'variant':'clavius-frame-repaired','mode':mode,'pose':'identity','native_time_s':0 if mode=='static' else .2,'all_body_mass_kg':434.92111389444585,'reported_rover_mass_kg':434.92111389444585,'maximum_joint_constraint_residual':0.,'maximum_shaft_speed_relation_error_rad_s':0.,'wheels':wheels,'flight_or_soil_validation':False},json.loads(PROTOCOL.read_text())


def test_consistent_frames_and_torque_are_only_component_evidence():
    raw,p=analytical_frames();r=score_frame(raw,p)
    assert r['checks_passed']
    assert not r['flight_prediction_validated'] and not r['lunar_soil_validated']


def test_reversed_left_wheel_axis_is_rejected_despite_consistent_inertia():
    raw,p=analytical_frames()
    for index in [0,2]:
        raw['wheels'][index]['shaft_axis_reference']=[0.,1.,0.]
        raw['wheels'][index]['shaft_axis_difference']=2.
        raw['wheels'][index]['wheel_omega_reference_rad_s']=[0.,-.3,0.]
    raw['maximum_shaft_speed_relation_error_rad_s']=.6
    r=score_frame(raw,p)
    assert r['checks']['collider_inertia_tensors']
    assert not r['checks']['shaft_reference_directions']
    assert not r['checks']['forward_torque_response']
    assert not r['checks_passed']


@pytest.mark.parametrize('case',['nan_clock','short_clock','nan_tensor','nan_shaft','missing_wheel','negative_residual','invented_metric','flight_claim'])
def test_incomplete_or_corrupt_native_evidence_is_rejected(case):
    raw,p=analytical_frames()
    if case=='nan_clock':raw['native_time_s']=float('nan')
    elif case=='short_clock':raw['native_time_s']=.1
    elif case=='nan_tensor':raw['wheels'][0]['body_inertia_reference_kg_m2'][0][0]=float('nan')
    elif case=='nan_shaft':raw['wheels'][0]['shaft_omega_rad_s']=float('nan')
    elif case=='missing_wheel':raw['wheels'].pop()
    elif case=='negative_residual':raw['maximum_joint_constraint_residual']=-1.
    elif case=='invented_metric':raw['wheels'][0]['cog_difference_m']=1.
    else:raw['flight_or_soil_validation']=True
    with pytest.raises(ValueError):score_frame(raw,p)
