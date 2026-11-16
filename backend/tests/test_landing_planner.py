import numpy as np
import pytest

from clavius.api import app
from clavius.drive_environment import drive_sample, start_epoch
from clavius.landing_planner import LandingSearch, exclusions, longest_gap, ranked_options, windows
from clavius.terrain import site
from fastapi.testclient import TestClient
from test_expedition import result

client = TestClient(app)


def test_interpolated_visibility_and_outages():
    rows = [{'t_s':i*60, 'clear':v} for i,v in enumerate([-1,1,1,-1])]
    visible = windows(rows, 'clear')
    assert visible == [[30,150]]
    assert longest_gap(visible,180) == 30
    assert longest_gap([],180) == 180
    assert longest_gap([[0,180]],180) == 0


def test_preferences_and_limits():
    request = LandingSearch(landing_utc='2028-01-01T00:00Z')
    base = dict(exclusions=[], slope_deg=2, longest_outage_hours=1, equivalent_sun_hours=1)
    a = dict(base,key='a',level_solar_wh_m2=250,tracking_solar_wh_m2=300,contact_hours=6,delta_v_km_s=8)
    b = dict(base,key='b',level_solar_wh_m2=150,tracking_solar_wh_m2=400,contact_hours=20,delta_v_km_s=9)
    assert ranked_options([a,b], request) == ['b','a']
    for preference, mount, winner in [('sunlight','level','a'),('sunlight','tracking','b'),('delta_v','level','a')]:
        assert ranked_options([a,b],request.model_copy(update=dict(priority=preference,array_mount=mount)))[0] == winner
    limited = request.model_copy(update=dict(max_delta_v_km_s=7,max_slope_deg=1,min_sun_hours=3,max_outage_hours=0))
    assert len(exclusions(a,limited)) == 4
    assert ranked_options([{**a,'exclusions':exclusions(a,limited)}, {'unavailable':'missing'}],limited) == []


def test_real_search_and_immutable_handoff():
    plan = result(client.post('/api/v1/landing-plans',json={'landing_utc':'2028-01-01T00:00Z',
                  'date_spacing_days':7,'surface_hours':2,'priority':'delta_v'}))
    assert len(plan['ranked_keys']) == len(plan['candidates']) == 6
    best = next(r for r in plan['candidates'] if r['key']==plan['ranked_keys'][0])
    assert best['delta_v_km_s'] == min(p['delta_v_km_s'] for r in plan['candidates'] for p in r['paths'] if 'unavailable' not in p)
    assert all(len(r['paths'])==3 for r in plan['candidates'])
    terrain=site(best['site_id'])
    sample=drive_sample(terrain, start_epoch(best['landing_utc']),0,0)
    assert best['samples'][0]['sun_horizon_deg']==sample['sun_horizon_deg']
    assert best['samples'][0]['earth_elevation_deg']==sample['earth_elevation_deg']
    assert best['slope_deg']==pytest.approx(float(terrain.slope(0,0)))
    reference_energy=np.trapezoid([s['level_irradiance_w_m2'] for s in best['samples']], dx=best['sample_step_s']/3600)
    assert best['level_solar_wh_m2']==pytest.approx(reference_energy)
    assert plan['sites'][best['site_id']]['terrain_sha256']
    url=f"/api/v1/landing-plans/{plan['id']}/options/"
    flight=client.post(url+best['key']).json()
    assert client.post(url+best['key']).json()['id']==flight['id']
    assert len(flight['trajectory_3d']['times_seconds'])==391
    assert flight['total_delta_v_km_s']==best['delta_v_km_s']
    assert start_epoch(flight['landing']['utc'])==pytest.approx(start_epoch(best['landing_utc']),rel=0,abs=.001)
    assert flight['planning_selection']['contact_hours']==best['contact_hours']
    assert flight['planning_selection']['incident_wh_m2']==best['level_solar_wh_m2']
    assert flight['planning_selection']['solved_flight_sha256']==best['flight_sha256']
    assert client.post(url+'unknown').status_code==409


@pytest.mark.parametrize('utc,target', [('2028-01-20T14:00Z','sun'), ('2028-01-13T06:00Z','earth')])
def test_sampled_event_cadence_at_two_real_crossings(utc, target):
    terrain=site('connecting-ridge')
    et=start_epoch(utc)
    def crossing(step):
        rows=[]
        for t in range(0,3601,step):
            s=drive_sample(terrain,et+t,0,0)
            margin=s[target+'_elevation_deg']-s[target+'_horizon_deg']
            if target=='sun':
                margin+=s['sun_angular_radius_deg']
            rows.append({'t_s':t,'clearance':margin})
        transitions=[t for interval in windows(rows,'clearance') for t in interval if t not in (0,3600)]
        assert len(transitions)==1
        return transitions[0]
    fine=crossing(60)
    for step in (600,1800):
        assert abs(crossing(step)-fine)<60


def test_all_paths_outside_budget_have_no_recommendation():
    plan=result(client.post('/api/v1/landing-plans',json={
        'landing_utc':'2028-01-01T00:00Z','surface_hours':1,'max_delta_v_km_s':1}))
    assert not plan['ranked_keys']
    for row in plan['candidates']:
        assert 'Transfer Δv exceeds limit' in row['exclusions']
        assert client.post(f"/api/v1/landing-plans/{plan['id']}/options/{row['key']}").status_code==409
