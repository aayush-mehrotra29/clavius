"""Published full-surface clones, native support masks and independent audit cases."""
import copy,io,json,os,subprocess,sys,zipfile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from clavius import store
from clavius.api import app
from clavius.paths import ROOT
from clavius.robots import import_robot
from clavius.terrain import site,stereographic,TerrainCoverageError
from clavius.mission import MissionRequest,evaluate
from clavius.dynamics import SegmentRequest,simulate_segment
from clavius.gazebo_package import make_packet,read_packet,canonical_hash
from clavius.scenarios import SweepRequest,sweep
from clavius.repairs import RepairSearchRequest,search,audit_cases,audit_request

@pytest.fixture(scope='module')
def rover():return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))

def mission(rover,**extra):return MissionRequest(robot_id=rover['id'],site_id='shackleton-rim',duration_hours=.02,waypoints=[{'east_m':0,'north_m':0}],activities=[],**extra)
def save(result,kind='mission'):return store.put('run',{**result,'artifact_sha256':store.artifact(result),'kind':kind})

@pytest.mark.parametrize('identity',['connecting-ridge','shackleton-rim'])
def test_published_clones_are_full_heights_in_one_fixed_nominal_frame(identity):
 nominal=site(identity);x,y=stereographic(nominal.lat,nominal.lon)
 for field in ['pgda78-0001','pgda78-0002','pgda78-0003']:
  clone=site(identity,field);np.testing.assert_array_equal(clone.origin,nominal.origin);np.testing.assert_array_equal(clone.rotation,nominal.rotation)
  difference=float(clone.local.sample(x,y))-float(nominal.local.sample(x,y))
  assert clone.height(0,0)==pytest.approx(difference,abs=1e-6)
  assert .01<abs(difference)<2
  assert abs(float(clone.local.sample(x,y)))>500 # full elevation, not a small error offset
  assert clone.manifest['realization']['id']==field
  assert clone.manifest['analysis_origin']==nominal.manifest['analysis_origin']
  assert clone.slope(0,0)!=pytest.approx(nominal.slope(0,0),abs=.01)
  assert len(clone.manifest['realization_catalogue'])==3


def test_native_counts_are_not_bilinearly_interpolated_or_replaced_by_rms():
 s=site();counts=s.counts;row,col=np.argwhere(counts.values>0)[300]
 x=counts.transform.c+(col+.5)*5;y=counts.transform.f-(row+.5)*5;actual=counts.values[row,col]
 assert actual>=1
 for dx,dy in [(-2.4,-2.4),(2.4,2.4),(0,0)]:assert counts.native_cell(x+dx,y+dy)==actual
 assert np.isnan(counts.native_cell(1e8,1e8))
 origin=s.sample(0,0);assert origin['covered'] and origin['nominal_lola_return_count']==0
 assert origin['height_rms_m']>0
 patch=s.patch(size=40);assert 0 in patch['nominal_lola_return_counts'] and any(c>0 for c in patch['nominal_lola_return_counts'])
 assert all(patch['nominal_height_supported']) and all(patch['height_uncertainty_supported'])


def test_local_clone_gap_cannot_be_filled_with_nominal_regional_terrain():
 # Deliberate missing-cell fixture on a copy; never changes the NASA cache.
 clone=copy.copy(site('shackleton-rim','pgda78-0001'));local=copy.copy(clone.local);local.values=local.values.copy();local.values[1390:1393,1267:1270]=np.nan;clone.local=local
 x,y=stereographic(clone.lat,clone.lon)
 with pytest.raises(TerrainCoverageError,match='realization support'):clone.local_horizon_sample(x,y)
 assert not clone.sample(0,0)['covered']
 with pytest.raises(TerrainCoverageError):clone.height(0,0)


def test_mission_recomputes_real_surface_slopes_horizons_and_positions(rover):
 base=evaluate(mission(rover),rover);changed=evaluate(mission(rover,scenario={'terrain_realization_id':'pgda78-0001'}),rover)
 assert changed['input_sha256']!=base['input_sha256']
 a,b=base['timeline'][0],changed['timeline'][0]
 assert a['t_s']==b['t_s']==0 and base['timeline'][-1]['t_s']==changed['timeline'][-1]['t_s']==72
 assert b['up_m']==pytest.approx(-.46044921875,abs=1e-6)
 assert a['slope_deg']!=pytest.approx(b['slope_deg'],abs=.01)
 assert abs(a['sun_horizon_deg']-b['sun_horizon_deg'])>1e-4 or abs(a['earth_horizon_deg']-b['earth_horizon_deg'])>1e-4
 assert b['nominal_lola_return_count']==0
 with pytest.raises(ValueError,match='not both'):mission(rover,scenario={'terrain_realization_id':'pgda78-0001','terrain_error_sigma':1})


def test_both_physics_paths_keep_the_requested_surface_and_reject_mixed_links(rover):
 request=SegmentRequest(robot_id=rover['id'],site_id='shackleton-rim',terrain_realization_id='pgda78-0001',duration_s=2)
 result=simulate_segment(request,rover);assert result['metrics']['contacts_observed'] and result['metrics']['distance_m']>.03
 assert result['provenance']['terrain']['realization']['id']==request.terrain_realization_id
 envelope=make_packet(request,rover);packet,_,grid=read_packet(envelope)
 assert grid['heights_m'][40,40]==pytest.approx(float(site(request.site_id,request.terrain_realization_id).height(0,0)),abs=1e-9)
 changed=copy.deepcopy(envelope);changed['payload']['request']['terrain_realization_id']='nominal';changed['sha256']=canonical_hash(changed['payload'])
 with pytest.raises(ValueError,match='realization'):read_packet(changed)
 with pytest.raises(ValueError,match='flat benchmark'):make_packet(request,rover,flat=True)
 parent=save(evaluate(mission(rover,scenario={'terrain_realization_id':'pgda78-0001'}),rover));client=TestClient(app)
 for endpoint in ['robot-segments','gazebo-packages']:
  response=client.post('/api/v1/'+endpoint,json={**request.model_dump(),'source_run_id':parent['id'],'terrain_realization_id':'nominal'})
  assert response.status_code==422 and 'realization' in response.json()['detail']
 sample=client.get('/api/v1/sites/shackleton-rim/sample?realization=pgda78-0001').json();assert sample['up_m']==pytest.approx(-.46044921875,abs=1e-6)
 assert sample['nominal_height_supported'] is True and sample['nominal_lola_return_count']==0


def test_sweep_balances_seeded_nominal_testing_pool_and_retains_unknown_cases(rover,monkeypatch):
 from clavius import scenarios
 req=SweepRequest(mission=mission(rover),samples=4);a=sweep(req,rover);b=sweep(req,rover)
 assert a['provenance']['terrain_ensemble']==b['provenance']['terrain_ensemble']
 ids=[c['scenario']['terrain_realization_id'] for c in a['outcomes']];assert ids.count('nominal')==ids.count('pgda78-0001')==2
 assert [c['input_sha256'] for c in a['outcomes']]==[c['input_sha256'] for c in b['outcomes']]
 real=evaluate
 def missing(request,*args,**kwargs):
  if request.scenario.terrain_realization_id=='pgda78-0001':raise TerrainCoverageError('Deliberate missing clone fixture')
  return real(request,*args,**kwargs)
 monkeypatch.setattr(scenarios,'evaluate',missing);unknown=sweep(req,rover)
 assert unknown['status']=='insufficient_evidence' and unknown['metrics']['unsupported_scenarios']==2
 assert all(c['run_id'] is None and 'missing clone' in c['reason'] for c in unknown['outcomes'] if c['status']=='insufficient_evidence')


def test_audit_terrain_is_excluded_from_nominal_candidate_selection(rover):
 base=mission(rover);request=RepairSearchRequest(source_run_id='0'*36,audit_samples=4)
 cases=audit_cases(request,base);assert {c['terrain_realization_id'] for c in cases}=={'pgda78-0002','pgda78-0003'}
 assert cases==audit_cases(request,base)
 audited=audit_request(base,cases[0]);assert audited.scenario.terrain_realization_id!='nominal' and audited.waypoints==base.waypoints
 with pytest.raises(ValueError,match='distinct'):audit_cases(request.model_copy(update={'audit_terrain_realization_ids':['nominal']}),base)
 alternate=base.model_copy(update={'scenario':base.scenario.model_copy(update={'terrain_realization_id':'pgda78-0002'})})
 assert {c['terrain_realization_id'] for c in audit_cases(request,alternate)}=={'pgda78-0003'}

@pytest.mark.parametrize('kind',['mission','campaign','repair'])
def test_captured_surface_catalogue_reproduces_mission_ensemble_and_audit(rover,kind,tmp_path):
 source_request=mission(rover,scenario={'terrain_realization_id':'pgda78-0001'})
 if kind=='mission':result=evaluate(source_request,rover)
 elif kind=='campaign':result=sweep(SweepRequest(mission=source_request,samples=2),rover)
 else:
  parent=save(evaluate(source_request,rover));result=search(RepairSearchRequest(source_run_id=parent['id'],date_offsets_days=[0],max_candidates=1,max_audit_candidates=1,audit_samples=2),rover,parent)
 record=save(result,kind);client=TestClient(app);response=client.get('/api/v1/runs/'+record['id']+'/export');assert response.status_code==200
 path=tmp_path/(kind+'.zip');path.write_bytes(response.content)
 with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
  captured=json.loads(archive.read('assessment.json'))['provenance']['terrain'];assert len(captured['realization_catalogue'])==3
 # Reproduction must replace the currently configured catalogue with the captured one.
 bad=tmp_path/'unrelated-catalogue.json';bad.write_text('{}')
 replay=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_simulation.py'),str(path)],env={**os.environ,'CLAVIUS_TERRAIN_MANIFEST_PATH':str(bad)},capture_output=True,text=True)
 assert replay.returncode==0,replay.stdout+replay.stderr
 assert json.loads(replay.stdout)['reproduced']


def test_render_support_pixels_and_projection_uv_match_native_source_cells():
 import hashlib,rasterio
 from clavius.terrain import scientific_manifest
 for identity in ['connecting-ridge','shackleton-rim']:
  s=site(identity);patch=s.patch(size=40);display=patch['nominal_support_display'];path=ROOT/'public'/display['file']
  assert hashlib.sha256(path.read_bytes()).hexdigest()==display['sha256']
  assert display['source_sha256']==patch['count_asset_sha256']
  with rasterio.open(path) as image:rgb=np.moveaxis(image.read(),0,-1)
  counts=s.counts.values
  # Every rendered native pixel has the exact source class, before lighting.
  np.testing.assert_array_equal(rgb[counts==0],np.tile(display['colors_srgb8']['interpolated'],((counts==0).sum(),1)))
  np.testing.assert_array_equal(rgb[counts>0],np.tile(display['colors_srgb8']['returns'],((counts>0).sum(),1)))
  uv=np.array(patch['nominal_support_uv']).reshape(patch['height'],patch['width'],2)
  for row,col in [(0,0),(4,4),(8,8),(0,8)]:
   e=patch['west_m']+col*5;n=patch['south_m']+row*5;lat,lon=s.location(e,n);x,y=stereographic(lat,lon)
   # PNG starts at the north edge; texture V runs upward. Check the flip explicitly.
   i=int(np.floor(uv[row,col,0]*display['width']));j=int(np.floor((1-uv[row,col,1])*display['height']))
   assert counts[j,i]==s.counts.native_cell(x,y)==patch['nominal_lola_return_counts'][row*patch['width']+col]
