import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from clavius.api import app, reference
from clavius.expedition import Target, TraverseRequest, WaypointDriver
from clavius.flight import FlightRequest, plan_flight
from clavius.geometry import epoch
from clavius.terrain import site

client = TestClient(app)


def solve(day, target):
    request = FlightRequest(departure_utc=day+'T00:00Z', site_id=target)
    return plan_flight(request, lambda *_: None, lambda: False)


def result(response):
    assert response.status_code == 200, response.text
    job = response.json()
    deadline = time.monotonic()+90
    while job['state'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(.05)
        job = client.get('/api/v1/jobs/'+job['id']).json()
    assert job['state'] == 'completed', job
    return client.get('/api/v1/runs/'+job['result_id']).json()


def test_transfer_depends_on_epoch_and_binds_to_measured_target():
    a = solve('2028-01-01','connecting-ridge')
    b = solve('2028-05-01','connecting-ridge')
    assert np.linalg.norm(np.array(a['trajectory_earth_j2000_km'][-1])-b['trajectory_earth_j2000_km'][-1]) > 10000
    for case in (a,b):
        assert max(case['endpoint_residual_m']) < 10
        assert case['minimum_central_radius_km'][0] > 6378
        landing = case['landing']
        assert landing['latitude_deg'] == site(landing['site_id']).lat
        assert epoch(landing['utc'])-epoch(case['approach_utc']) == pytest.approx(900,abs=.002)
        assert case['total_delta_v_km_s'] == sum(case['maneuvers_km_s'].values())


def test_public_workflow_uses_parent_epoch_site_and_actual_waypoints():
    flight = result(client.post('/api/v1/flights',json={'site_id':'shackleton-rim','departure_utc':'2028-01-02T12:00Z','transfer_hours':84}))
    request = {'flight_id':flight['id'], 'robot_id':reference['id'], 'waypoints':[{'east_m':1.,'north_m':1.}], 'task':'science','dwell_s':4}
    assert client.post('/api/v1/traverses',json={**request,'site_id':'connecting-ridge'}).status_code == 422
    assert client.post('/api/v1/traverses',json={**request,'flight_id':reference['id']}).status_code == 404
    run = result(client.post('/api/v1/traverses',json=request))
    assert run['flight_sha256'] == flight['artifact_sha256']
    assert run['landing'] == flight['landing']
    assert run['sources']['terrain_sha256'] == flight['sources']['terrain_sha256']
    assert run['engine']['name']=='MuJoCo' and run['metrics']['contacts_observed']
    assert run['task_completed'] and run['route_events'][-1]['completed_task']=='science'
    assert run['issues'] == []
    dwell = [row for row in run['trace'] if row['activity']=='science']
    assert dwell[-1]['t_s']-dwell[0]['t_s'] >= 4-1e-6
    assert all(np.hypot(row['east_m']-1,row['north_m']-1) <= .18 for row in dwell)
    assert run['trace'][-1]['t_s'] == run['metrics']['duration_s']
    assert 0 < run['metrics']['minimum_battery_wh'] <= run['metrics']['battery_capacity_wh']


def test_dwell_requires_continuous_presence_and_full_duration():
    req=TraverseRequest(flight_id='test',robot_id='test',waypoints=[Target(east_m=1,north_m=0)],task='wait',dwell_s=5)
    driver=WaypointDriver(req,.05)
    for t,east in [(0,1),(3,1),(4,1.3),(5,1),(9,1)]:
        driver.command(t,east,0,0)
        assert not driver.finished
    driver.command(10,1,0,0)
    assert driver.finished


def test_empty_battery_stops_motion_before_science():
    from copy import deepcopy
    from clavius.expedition import traverse

    flight=solve('2028-01-01','connecting-ridge')
    robot=deepcopy(reference)
    robot['profile']['power'].update(initial_soc_fraction=0,solar_rated_power_w=0)
    req=TraverseRequest(flight_id='probe',robot_id=robot['id'],waypoints=[Target(east_m=2,north_m=0)],task='science')
    run=traverse(req,{**flight,'id':'probe','artifact_sha256':'test'},robot,lambda *_:None,lambda:False)
    assert not run['task_completed'] and not run['route_events']
    assert run['trace'][-1]['t_s'] <= .05
    assert run['trace'][-1]['battery_wh'] == 0
    assert any('depleted' in issue for issue in run['issues'])


def test_flight_viewer_samples_follow_coasts_and_rotating_descent():
    import spiceypy as spice
    from clavius.flight import moon_state, saved_flight_samples

    flight = solve('2028-05-01', 'shackleton-rim')
    data = flight['trajectory_3d']
    times = np.array(data['times_seconds'])
    craft = np.array(data['spacecraft_coords_km'])
    moon = np.array(data['moon_coords_km'])
    velocities = np.array(data['spacecraft_velocities_kms'])
    lunar_v = np.array(data['moon_velocities_kms'])
    start = epoch(flight['departure_utc'])
    approach = data['approach_index']
    assert times[0] == 0 and np.diff(times).min() > 0
    assert times[-1] == pytest.approx(flight['transfer_s'])
    np.testing.assert_array_equal(craft[:approach+1], flight['trajectory_earth_j2000_km'])
    for i in (0, data['patch_index'], approach, len(times)-1):
        np.testing.assert_allclose(np.r_[moon[i], lunar_v[i]], moon_state(start+times[i]), atol=1e-8, rtol=0)
    assert 100 == pytest.approx(np.linalg.norm(craft[approach]-moon[approach])
                                -np.linalg.norm(craft[-1]-moon[-1]), abs=.01)
    fixed = spice.sxform('J2000', 'MOON_ME_DE421', start+times[-1]) @ np.r_[craft[-1]-moon[-1],velocities[-1]-lunar_v[-1]]
    np.testing.assert_allclose(fixed[:3], site('shackleton-rim').origin/1000, rtol=0, atol=1e-6)
    np.testing.assert_allclose(fixed[3:], 0, atol=1e-10)
    legacy = {key:value for key,value in flight.items() if key!='trajectory_3d'}
    assert saved_flight_samples(legacy) == data
    legacy['trajectory_earth_j2000_km']=[[0,0,0]]
    with pytest.raises(ValueError,match='could not be reproduced'):
        saved_flight_samples(legacy)
