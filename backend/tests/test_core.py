import io,json,zipfile
from pathlib import Path
import numpy as np
import pytest
from clavius.paths import ROOT
from clavius.robots import parse_urdf,import_robot,validate_profile,ImportIssue
from clavius.terrain import site,stereographic,body_latlon,latlon_body,basis
from clavius.geometry import epoch,directions,solar_disk_fraction,horizon_elevation
from clavius.mission import integrate_energy,MissionRequest,evaluate
from clavius.dynamics import SegmentRequest,simulate_segment

@pytest.fixture(scope='module')
def rover():
 return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))

def test_reference_urdf_properties(rover):
 assert rover['model']['mass_kg']==24
 assert rover['model']['physical_ready']
 assert len(rover['model']['joints'])==4
 np.testing.assert_allclose(rover['model']['center_of_mass_body_m'],[0,0,.36],atol=1e-12)

def test_zip_path_traversal_rejected():
 data=io.BytesIO()
 with zipfile.ZipFile(data,'w') as z:z.writestr('../unsafe.urdf','<robot/>')
 with pytest.raises(ImportIssue,match='inside'):parse_urdf(data.getvalue(),'robot.zip')

def test_entity_expansion_rejected():
 xml=b'<!DOCTYPE robot [<!ENTITY payload SYSTEM "file:///etc/passwd">]><robot name="&payload;"></robot>'
 with pytest.raises(ImportIssue,match='safely'):parse_urdf(xml,'bad.urdf')

def test_profile_impossible_reserve_rejected(rover):
 p=json.loads(json.dumps(rover['profile']));p['power']['reserve_wh']=501
 with pytest.raises(ImportIssue,match='reserve'):validate_profile(p)

def test_energy_exact_cases():
 assert integrate_energy(50,100,0,3600,200,.9,.8)==(140,90)
 assert integrate_energy(150,0,40,3600,200,.9,.8)==(100,-50)
 assert integrate_energy(190,100,0,3600,200,.9,.8)[0]==200
 assert integrate_energy(10,0,100,3600,200,.9,.8)[0]==0

def test_coordinate_frames_and_origin():
 s=site();np.testing.assert_allclose(s.rotation.T@s.rotation,np.eye(3),atol=1e-12)
 assert np.linalg.det(s.rotation)>0
 assert abs(float(s.height(0,0)))<1e-6
 for lat,lon in [(-89.44,222.8),(-80,45),(0,180)]:
  a,b=body_latlon(latlon_body(lat,lon));assert abs(a-lat)<1e-9
  assert abs((b-lon+180)%360-180)<1e-9
 assert max(abs(c['difference_m']) for c in s.manifest['vertical_checks'])<2

@pytest.mark.parametrize('elevation,fraction',[(-1,0),(0,.5),(1,1)])
def test_finite_solar_disk(elevation,fraction):
 assert solar_disk_fraction(elevation,0,.27)==fraction

def test_horizon_wrap():
 p={'elevations_deg':[0,1,2,3],'azimuth_step_deg':90}
 assert horizon_elevation(p,360)==0
 assert horizon_elevation(p,-45)==1.5

def test_spice_unit_directions_and_time():
 s=site();et=epoch('2028-01-01T00:00:00Z');g=directions(et,s.lat,s.lon,s.origin_height_m)
 for body in ['sun','earth']:assert np.linalg.norm(g[body]['enu'])==pytest.approx(1)
 assert 0<g['sun']['angular_radius_deg']<1
 assert 1<g['earth_light_time_s']<2
 assert epoch('2028-01-01T00:01:00Z')-et==pytest.approx(60,abs=.001)

def test_real_site_mission_and_energy_independent_reintegration(rover):
 request=MissionRequest(robot_id=rover['id'],duration_hours=.1,waypoints=[{'east_m':0,'north_m':0},{'east_m':5,'north_m':0}],activities=[])
 result=evaluate(request,rover)
 assert result['status']=='supported_under_assumptions'
 assert result['metrics']['distance_m']>5
 assert result['metrics']['scheduled_completion_s']<request.duration_hours*3600
 assert result['timeline'][0]['t_s']==0
 assert result['timeline'][-1]['t_s']==360
 assert all(a['t_s']<b['t_s'] for a,b in zip(result['timeline'],result['timeline'][1:]))
 energy=425.
 for a,b in zip(result['timeline'],result['timeline'][1:]):
  net=a['solar_w']-a['load_w'];energy+=net*(.94 if net>=0 else 1/.95)*(b['t_s']-a['t_s'])/3600
  energy=min(500,max(0,energy))
 assert energy==pytest.approx(result['metrics']['final_battery_wh'])
 assert result['provenance']['terrain']['assets'][0]['resolution_m']==5
 assert result['provenance']['kernels']['ephemeris']=='DE421'

def test_battery_failure_has_crossing_time(rover):
 robot=json.loads(json.dumps(rover));robot['profile']['power'].update(battery_capacity_wh=10,initial_soc_fraction=.9,reserve_wh=5,solar_rated_power_w=0)
 request=MissionRequest(robot_id=rover['id'],duration_hours=.5,waypoints=[{'east_m':0,'north_m':0}],activities=[])
 result=evaluate(request,robot)
 event=next(e for e in result['events'] if e['code']=='BATTERY_RESERVE')
 assert event['t_s']==pytest.approx((9-5)*.95/(12+8)*3600)
 assert result['status']=='constraint_violated'
 assert result['metrics']['minimum_battery_wh']==0

def test_flat_lunar_weight_and_drive(rover):
 request=SegmentRequest(robot_id=rover['id'],duration_s=5)
 result=simulate_segment(request,rover,flat=True)
 last=result['trace'][-1]
 assert result['engine']['name']=='MuJoCo'
 assert result['metrics']['contacts_observed']
 assert last['total_contact_normal_n']==pytest.approx(24*1.62,rel=.01)
 assert last['speed_m_s']==pytest.approx(.05,rel=.05)
 assert .20<result['metrics']['distance_m']<.27
 assert result['metrics']['maximum_roll_deg']<.1
 assert len(last['joint_positions'])==4


def test_real_terrain_segment_executes(rover):
 result=simulate_segment(SegmentRequest(robot_id=rover['id'],duration_s=3),rover)
 assert result['metrics']['contacts_observed']
 assert result['metrics']['distance_m']>.05
 assert result['provenance']['terrain']['site_id']=='connecting-ridge'

def test_api_epoch_with_timezone_offset_normalizes_for_spice(rover):
 req=MissionRequest(robot_id=rover['id'],start_utc='2028-01-01T01:00:00+01:00')
 assert req.start_utc=='2028-01-01T00:00:00Z'
 assert epoch(req.start_utc)==epoch('2028-01-01T00:00:00Z')

def test_mesh_collision_conversion_is_executed_and_recorded(rover):
 import trimesh
 source=(ROOT/'public/robots/clavius-r1.urdf').read_text()
 source=source.replace('<collision><origin xyz="0 0 0.4"/><geometry><box size="0.85 0.56 0.22"/></geometry></collision>','<collision><origin xyz="0 0 0.4"/><geometry><mesh filename="body.stl"/></geometry></collision>')
 raw=io.BytesIO()
 with zipfile.ZipFile(raw,'w') as z:
  z.writestr('rover.urdf',source)
  z.writestr('body.stl',trimesh.creation.box(extents=[.85,.56,.22]).export(file_type='stl'))
 imported=import_robot(raw.getvalue(),'mesh-rover.zip',rover['profile'])
 result=simulate_segment(SegmentRequest(robot_id=imported['id'],duration_s=1),imported,flat=True)
 assert result['metrics']['contacts_observed']
 assert result['collision_conversions'][0]['method'].startswith('single convex hull')
 assert len(result['collision_conversions'][0]['sha256'])==64
