"""Cross-module acceptance cases using real site data and executed physics."""
import copy,io,json,zipfile
import numpy as np
import pytest
from clavius.paths import ROOT
from clavius import store
from clavius.robots import import_robot,parse_urdf,revise_mechanics,ImportIssue
from clavius.mission import MissionRequest,build_schedule,pose_at,evaluate
from clavius.scenarios import SweepRequest,sweep
from clavius.terrain import site
from clavius.geometry import directions,epoch

@pytest.fixture
def rover():
 return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))

def test_mechanical_revision_changes_mass_and_preserves_old_artifact(rover):
 old=copy.deepcopy(rover);revised=revise_mechanics(rover,[{'link':'base_link','mass_kg':21,'inertia_kg_m2':[1.45,2.1,2.8,0,0,0],'origin_xyz_m':[0,0,.4]}])
 assert revised['id']!=old['id']
 assert revised['model']['mass_kg']==revised['profile']['mass_kg']==25
 assert revised['parent_robot_id']==old['id']
 assert store.get(old['id'])==old
 assert revised['profile']['center_of_mass_body_m']==revised['model']['center_of_mass_body_m']
 with pytest.raises(ImportIssue,match='inertia'):
  revise_mechanics(rover,[{'link':'base_link','mass_kg':21,'inertia_kg_m2':[1,1,9,0,0,0]}])

def test_mesh_external_dependencies_are_rejected():
 source=(ROOT/'public/robots/clavius-r1.urdf').read_text().replace('<box size="0.85 0.56 0.22"/>','<mesh filename="body.gltf"/>')
 raw=io.BytesIO()
 with zipfile.ZipFile(raw,'w') as z:
  z.writestr('rover.urdf',source);z.writestr('body.gltf',json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':'https://example.com/untrusted.bin','byteLength':4}]}))
 with pytest.raises(ImportIssue,match='inside'):parse_urdf(raw.getvalue(),'unsafe.zip')

def test_duplicate_waypoint_keeps_its_activity_and_stationary_heading(rover):
 req=MissionRequest(robot_id=rover['id'],waypoints=[{'east_m':0,'north_m':0},{'east_m':0,'north_m':0},{'east_m':0,'north_m':5}],activities=[{'kind':'science','waypoint':1,'duration_s':30},{'kind':'radio','waypoint':2,'duration_s':40}])
 phases,_,_=build_schedule(req,rover['profile'],site())
 assert phases[0]['kind']=='science' and phases[0]['end_s']==30
 assert phases[-1]['heading_rad']==pytest.approx(np.pi/2)
 # Sampling a later phase must not change the heading returned for an earlier one.
 assert pose_at(0,phases)[1]['heading_rad']==0
 assert pose_at(100000,phases)[1]['heading_rad']==pytest.approx(np.pi/2)

def test_real_horizon_radial_convergence_and_layer_values():
 terrain=site();point=terrain.sample(0,0);g=directions(epoch('2028-01-14T00:00:00Z'),terrain.lat,terrain.lon,float(point['elevation_m'])+.5)
 az=[g['sun']['azimuth_deg'],g['earth']['azimuth_deg']]
 base=terrain.horizon_directions(0,0,az);fine=terrain.horizon_directions(0,0,az,refinement=2)
 assert np.max(np.abs(base-fine))<.02
 patch=terrain.patch(size=40)
 assert len(patch['heights_m'])==len(patch['slopes_deg'])==len(patch['height_rms_m'])==81
 assert min(patch['height_rms_m'])>0

def test_contact_limit_is_reported_at_first_crossing(rover):
 result=evaluate(MissionRequest(robot_id=rover['id'],start_utc='2028-01-14T00:00:00Z',duration_hours=.1,max_earth_outage_s=120,waypoints=[{'east_m':0,'north_m':0}],activities=[]),rover)
 assert result['first_violation']['code']=='CONTACT_OUTAGE_LIMIT'
 assert result['first_violation']['t_s']==120
 assert result['metrics']['longest_earth_outage_s']==360

def test_sweep_has_reproducible_inputs_and_replayable_children(rover):
 mission=MissionRequest(robot_id=rover['id'],duration_hours=.02,waypoints=[{'east_m':0,'north_m':0}],activities=[])
 request=SweepRequest(mission=mission,samples=2,seed=10)
 a=sweep(request,rover);b=sweep(request,rover)
 for left,right in zip(a['outcomes'],b['outcomes']):
  assert left['input_sha256']==right['input_sha256']
  assert left['metrics']==right['metrics']
  assert store.get(left['run_id'])['timeline']
 assert a['provenance']['kernels']['ephemeris']=='DE421'

def test_relative_mesh_paths_stay_inside_the_package():
 import trimesh
 source=(ROOT/'public/robots/clavius-r1.urdf').read_text().replace('<box size="0.85 0.56 0.22"/>','<mesh filename="../meshes/body.stl"/>')
 raw=io.BytesIO()
 with zipfile.ZipFile(raw,'w') as z:
  z.writestr('urdf/rover.urdf',source);z.writestr('meshes/body.stl',trimesh.creation.box().export(file_type='stl'))
 model,_=parse_urdf(raw.getvalue(),'relative.zip')
 assert model['links'][0]['visuals'][0]['file']=='meshes/body.stl'

def test_root_link_above_ground_datum_is_placed_from_colliders(rover):
 from clavius.dynamics import SegmentRequest,simulate_segment
 source=(ROOT/'public/robots/clavius-r1.urdf').read_text().replace('xyz="0 0 0.4"','xyz="0 0 0"').replace('0.37 0.16"','0.37 -0.24"').replace('-0.37 0.16"','-0.37 -0.24"')
 profile=copy.deepcopy(rover['profile']);profile['center_of_mass_body_m']=[0,0,-.04]
 model=import_robot(source.encode(),'raised-root.urdf',profile)
 result=simulate_segment(SegmentRequest(robot_id=model['id'],duration_s=3),model,flat=True)
 assert result['metrics']['contacts_observed']
 assert result['trace'][-1]['up_m']==pytest.approx(.4,abs=.01)
 assert result['trace'][-1]['total_contact_normal_n']==pytest.approx(24*1.62,rel=.02)
 assert result['metrics']['distance_m']>.1

def test_shared_clock_keeps_known_utc_leap_second(rover):
 result=evaluate(MissionRequest(robot_id=rover['id'],start_utc='2016-12-31T23:59:00Z',duration_hours=.05,waypoints=[{'east_m':0,'north_m':0}],activities=[]),rover)
 assert any(row['utc']=='2016-12-31T23:59:60.000Z' for row in result['timeline'])
 assert any(row['utc']=='2017-01-01T00:00:00.000Z' for row in result['timeline'])
 assert result['timeline'][-1]['t_s']==180
 assert result['timeline'][-1]['utc'].startswith('2017-01-01T00:01:59.')
