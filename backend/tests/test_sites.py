"""Real Site04 sources, distinct frames, and saved mission/worker identity checks."""
import copy,io,json,os,subprocess,sys,zipfile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from clavius.api import app
from clavius import store
from clavius.terrain import site,stereographic,definition,roi_origin,DATA,TerrainCoverageError
from clavius.diviner import sample as thermal_context,load
from clavius.mission import MissionRequest,evaluate,integrate_energy
from clavius.dynamics import SegmentRequest,simulate_segment
from clavius.gazebo_package import make_packet,read_packet,canonical_hash
from clavius.robots import import_robot
from clavius.paths import ROOT

@pytest.fixture(scope='module')
def rover():return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))

def test_shackleton_origin_is_published_anchor_and_native_pixel_center():
 s=site('shackleton-rim');d=definition(s.id);x,y=roi_origin(DATA/'raw/Site04_ROIs.tgz',4)
 assert (x,y)==(-2657.5,-5957.5)
 np.testing.assert_allclose(stereographic(s.lat,s.lon),[x,y],atol=1e-6)
 check=s.manifest['origin_registration_check'];assert (check['pixel_column'],check['pixel_row'])==(1268,1391)
 assert check['conversion_residual_m']<1e-6
 assert float(s.local.values[1391,1268])==pytest.approx(s.origin_height_m,abs=1e-6)
 assert s.origin_height_m==pytest.approx(1737.2283935546875)
 assert abs(float(s.height(0,0)))<1e-6
 np.testing.assert_allclose(s.rotation.T@s.rotation,np.eye(3),atol=1e-12)
 assert max(abs(p['difference_m']) for p in s.manifest['vertical_checks'])==pytest.approx(4.46044921875)
 patch=s.patch();assert patch['source_id']=='PGDA78-Site04'
 assert patch['height_range_m'][0]<-150 and np.isfinite(patch['height_rms_m']).all()
 with pytest.raises(TerrainCoverageError):s.height(100000,100000)
 assert s.regional is site('connecting-ridge').regional
 assert np.linalg.norm(s.origin-site('connecting-ridge').origin)>10000

@pytest.mark.parametrize('identity',['connecting-ridge','shackleton-rim'])
def test_each_site_mission_uses_own_geography_clock_and_energy(rover,identity):
 s=site(identity);request=MissionRequest(robot_id=rover['id'],site_id=identity,duration_hours=.02,waypoints=[{'east_m':0,'north_m':0}],activities=[])
 result=evaluate(request,rover);first=result['timeline'][0]
 assert result['provenance']['terrain']['definition']==definition(identity)
 assert first['lat_deg']==pytest.approx(s.lat,abs=1e-8)
 assert first['lon_deg']==pytest.approx(s.lon,abs=1e-8)
 assert result['timeline'][-1]['t_s']==72
 energy=425.
 for a,b in zip(result['timeline'],result['timeline'][1:]):energy=integrate_energy(energy,a['solar_w'],a['load_w'],b['t_s']-a['t_s'],500,.94,.95)[0]
 assert energy==pytest.approx(result['metrics']['final_battery_wh'])


def test_shackleton_diviner_is_separate_clip_and_cross_site_ref_is_rejected(rover):
 s=site('shackleton-rim');spec,data=load(s.id)
 assert [len(p['samples']) for p in data['products']]==[386,327]
 context=thermal_context(s.lat,s.lon,s.id)
 assert context['source_manifest']['selected_site_id']==s.id
 covered=next(b for b in context['bins'] if b['covered'])
 thermal={'ground_temperature_c':covered['temperature_c'],'ground_reference':covered['reference']}
 result=evaluate(MissionRequest(robot_id=rover['id'],site_id=s.id,duration_hours=.02,thermal=thermal,waypoints=[{'east_m':0,'north_m':0}],activities=[]),rover)
 assert result['provenance']['diviner']['derivative']['sha256']==spec['derivative']['sha256']
 with pytest.raises(ValueError,match='different site'):evaluate(MissionRequest(robot_id=rover['id'],duration_hours=.02,thermal=thermal),rover)
 assert not any(b['covered'] for b in thermal_context(-89.44,222.8,s.id)['bins'])


def test_shackleton_dynamics_packet_and_link_reject_mixed_sites(rover):
 request=SegmentRequest(robot_id=rover['id'],site_id='shackleton-rim',duration_s=2)
 result=simulate_segment(request,rover)
 assert result['provenance']['terrain']['site_id']=='shackleton-rim'
 assert result['metrics']['contacts_observed'] and result['metrics']['distance_m']>.03
 envelope=make_packet(request,rover);packet,_,prepared=read_packet(envelope)
 assert packet.terrain.source_manifest['site_id']==request.site_id
 assert prepared['heights_m'][40,40]==pytest.approx(float(site(request.site_id).height(0,0)),abs=1e-9)
 altered=copy.deepcopy(envelope);altered['payload']['request']['site_id']='connecting-ridge';altered['sha256']=canonical_hash(altered['payload'])
 with pytest.raises(ValueError,match='site'):read_packet(altered)
 parent=evaluate(MissionRequest(robot_id=rover['id'],site_id=request.site_id,duration_hours=.02,waypoints=[{'east_m':0,'north_m':0}],activities=[]),rover);parent=store.put('run',{'kind':'mission','artifact_sha256':store.artifact(parent),**parent})
 client=TestClient(app)
 for endpoint in ['robot-segments','gazebo-packages']:
  response=client.post('/api/v1/'+endpoint,json={'robot_id':rover['id'],'site_id':'connecting-ridge','source_run_id':parent['id'],'duration_s':2})
  assert response.status_code==422 and 'site' in response.json()['detail']
 linked=client.post('/api/v1/gazebo-packages',json={**request.model_dump(),'source_run_id':parent['id'],'mission_offset_s':10})
 assert linked.status_code==200


def test_shackleton_export_pins_origin_sources_and_thermal_clip_for_reproduction(rover,tmp_path):
 s=site('shackleton-rim');context=thermal_context(s.lat,s.lon,s.id);b=next(b for b in context['bins'] if b['covered'])
 request=MissionRequest(robot_id=rover['id'],site_id=s.id,duration_hours=.02,thermal={'ground_temperature_c':b['temperature_c'],'ground_reference':b['reference']},waypoints=[{'east_m':0,'north_m':0}],activities=[])
 result=evaluate(request,rover);result=store.put('run',{'kind':'mission','artifact_sha256':store.artifact(result),**result});client=TestClient(app)
 catalog=client.get('/api/v1/sites').json();assert {e['id'] for e in catalog if e['available']}=={'connecting-ridge','shackleton-rim'}
 response=client.get('/api/v1/runs/'+result['id']+'/export');assert response.status_code==200
 path=tmp_path/'site04-evidence.zip';path.write_bytes(response.content)
 with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
  assert 'context/diviner-shackleton-rim.json' in archive.namelist()
  assert json.loads(archive.read('assessment.json'))['provenance']['terrain']['definition']==definition(s.id)
 reproduced=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_simulation.py'),str(path)],env=os.environ,capture_output=True,text=True)
 assert reproduced.returncode==0,reproduced.stdout+reproduced.stderr
 assert json.loads(reproduced.stdout)['reproduced']
