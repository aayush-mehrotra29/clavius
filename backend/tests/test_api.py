import io,json,time,zipfile
import pytest
from fastapi.testclient import TestClient
from clavius.api import app
from clavius.paths import ROOT
client=TestClient(app)
def complete(job_id):
 for _ in range(200):
  job=client.get('/api/v1/jobs/'+job_id).json()
  if job['state'] in {'completed','failed','cancelled'}:return job
  time.sleep(.05)
 raise AssertionError('Job did not finish in the integration-test budget.')
def test_http_real_mission_saved_and_exported():
 health=client.get('/api/v1/health').json();robot_id=health['reference_robot_id']
 response=client.post('/api/v1/planning-runs',json={'robot_id':robot_id,'start_utc':'2028-01-01T01:00:00+01:00','duration_hours':.1,'waypoints':[{'east_m':0,'north_m':0}],'activities':[]})
 assert response.status_code==200
 job=complete(response.json()['id']);assert job['state']=='completed',job
 result=client.get('/api/v1/runs/'+job['result_id']).json()
 assert result['time_origin_utc'].startswith('2028-01-01T00:00:00')
 assert len(result['timeline'])>2
 response=client.get('/api/v1/runs/'+job['result_id']+'/export');assert response.status_code==200
 with zipfile.ZipFile(io.BytesIO(response.content)) as z:
  evidence=json.loads(z.read('assessment.json'));assert evidence['input_sha256']==result['input_sha256']
  assert 'robot.json' in z.namelist()
def test_robot_upload_and_bad_time_rejection():
 response=client.post('/api/v1/robots',files={'package':('r1.zip',(ROOT/'public/robots/clavius-r1.zip').read_bytes(),'application/zip')})
 assert response.status_code==200,response.text
 assert response.json()['profile']['robot_id']=='clavius-r1'
 bad=client.post('/api/v1/planning-runs',json={'robot_id':response.json()['id'],'start_utc':'2028-01-01T00:00:00'})
 assert bad.status_code==422

def test_selected_mission_segment_retains_clock_position_and_robot():
 from clavius.geometry import epoch
 robot_id=client.get('/api/v1/health').json()['reference_robot_id']
 mission=client.post('/api/v1/planning-runs',json={'robot_id':robot_id,'duration_hours':.1,'waypoints':[{'east_m':0,'north_m':0},{'east_m':0,'north_m':5}],'activities':[]}).json()
 parent=complete(mission['id']);assert parent['state']=='completed',parent
 source=client.get('/api/v1/runs/'+parent['result_id']).json()
 job=client.post('/api/v1/robot-segments',json={'robot_id':robot_id,'source_run_id':source['id'],'mission_offset_s':40,'duration_s':2}).json()
 finished=complete(job['id']);assert finished['state']=='completed',finished
 result=client.get('/api/v1/runs/'+finished['result_id']).json()
 assert result['request']['north_m']==__import__('pytest').approx(2,abs=.02)
 assert result['request']['heading_deg']==__import__('pytest').approx(90)
 assert epoch(result['time_origin_utc'])-epoch(source['time_origin_utc'])==__import__('pytest').approx(40,abs=.001)
 assert result['trace'][0]['mission_t_s']>40
 assert result['source_mission']['input_sha256']==source['input_sha256']
 invalid=client.post('/api/v1/robot-segments',json={'robot_id':robot_id,'source_run_id':source['id'],'mission_offset_s':359,'duration_s':2})
 assert invalid.status_code==422

def test_job_can_be_cancelled_without_an_accepted_partial_run(monkeypatch):
 from clavius import api
 def long_work(request,robot,progress,cancel):
  for i in range(100):
   progress(i/100,'Cancellation acceptance case');time.sleep(.02)
  raise AssertionError('Work should have been cancelled.')
 monkeypatch.setattr(api,'evaluate',long_work)
 robot_id=client.get('/api/v1/health').json()['reference_robot_id']
 job=client.post('/api/v1/planning-runs',json={'robot_id':robot_id}).json()
 client.post('/api/v1/jobs/'+job['id']+'/cancel')
 finished=complete(job['id'])
 assert finished['state']=='cancelled'
 assert finished['result_id'] is None

@pytest.mark.parametrize('thermal',[None,{'initial_temperature_c':1,'heat_capacity_j_k':1000},'diviner'])
def test_export_contains_recorded_source_and_can_reproduce_metrics(tmp_path,thermal):
 import os,subprocess,sys
 if thermal=='diviner':
  context=client.get('/api/v1/sites/connecting-ridge/thermal-context').json()['bins'][0]
  thermal={'ground_temperature_c':context['temperature_c'],'ground_reference':context['reference']}
 robot_id=client.get('/api/v1/health').json()['reference_robot_id']
 job=client.post('/api/v1/planning-runs',json={'robot_id':robot_id,'duration_hours':.02,'thermal':thermal,'waypoints':[{'east_m':0,'north_m':0}],'activities':[]}).json()
 finished=complete(job['id']);assert finished['state']=='completed',finished
 payload=client.get('/api/v1/runs/'+finished['result_id']+'/export').content
 path=tmp_path/'evidence.zip';path.write_bytes(payload)
 with zipfile.ZipFile(io.BytesIO(payload)) as z:
  assert 'implementation/clavius/mission.py' in z.namelist()
  assert 'robot-package/original-upload.bin' in z.namelist()
  if thermal and thermal.get('ground_reference'):
   assert {'context/diviner-manifest.json','context/diviner-connecting-ridge.json'}<=set(z.namelist())
 result=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_simulation.py'),str(path)],capture_output=True,text=True,env=os.environ)
 assert result.returncode==0,result.stdout+result.stderr
 assert json.loads(result.stdout)['reproduced']

def test_gazebo_cannot_silently_run_mujoco_when_worker_is_missing(monkeypatch):
 monkeypatch.delenv('CLAVIUS_GAZEBO_URL',raising=False)
 health=client.get('/api/v1/health').json()
 assert not health['physics_engines']['gazebo']['available']
 response=client.post('/api/v1/robot-segments',json={'robot_id':health['reference_robot_id'],'engine':'gazebo','duration_s':2})
 assert response.status_code==409
 assert 'worker' in response.json()['detail'].lower()

def test_gazebo_review_package_is_exportable_without_executing_physics():
 health=client.get('/api/v1/health').json()
 response=client.post('/api/v1/gazebo-packages',json={'robot_id':health['reference_robot_id'],'engine':'gazebo','duration_s':2})
 assert response.status_code==200,response.text
 with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
  assert {'packet.json','world.sdf','world-manifest.json','terrain.dae','README.txt'}<=set(archive.namelist())
  assert 'does not prove Gazebo execution' in archive.read('README.txt').decode()
  packet=json.loads(archive.read('packet.json'));assert packet['payload']['request']['engine']=='gazebo'
  assert packet['payload']['terrain']['native_resolution_m']==5


def test_thermal_properties_endpoint_validates_cross_field_constraints():
 model=client.get('/api/v1/thermal-model').json()
 assert model['source_class']=='declared_engineering_scenario'
 assert model['defaults']['schema_version']=='clavius-thermal-1'
 response=client.post('/api/v1/thermal-model/validate',json=model['defaults'])
 assert response.status_code==200
 assert response.json()==model['defaults']
 invalid={**model['defaults'],'heater_off_c':model['defaults']['heater_on_c']}
 assert client.post('/api/v1/thermal-model/validate',json=invalid).status_code==422

@pytest.mark.parametrize('diviner',[False,True])
def test_http_repair_search_exports_and_reproduces_every_candidate(tmp_path,diviner):
 import os,subprocess,sys
 robot_id=client.get('/api/v1/health').json()['reference_robot_id']
 thermal=None
 if diviner:
  context=client.get('/api/v1/sites/connecting-ridge/thermal-context').json()['bins'][0]
  thermal={'ground_temperature_c':context['temperature_c'],'ground_reference':context['reference']}
 mission=client.post('/api/v1/planning-runs',json={'robot_id':robot_id,'thermal':thermal,'start_utc':'2028-01-14T00:00:00Z','duration_hours':.1,'max_earth_outage_s':120,'waypoints':[{'east_m':0,'north_m':0}],'activities':[{'kind':'science','waypoint':0,'duration_s':60}]}).json()
 source=complete(mission['id']);assert source['state']=='completed'
 request={'source_run_id':source['result_id'],'date_offsets_days':[-13,0],'max_candidates':2,'max_audit_candidates':1,'audit_samples':2}
 response=client.post('/api/v1/repair-searches',json=request);assert response.status_code==200,response.text
 job=complete(response.json()['id']);assert job['state']=='completed',job
 result=client.get('/api/v1/runs/'+job['result_id']).json()
 assert result['kind']=='repair' and result['recommended_candidate_id']
 payload=client.get('/api/v1/runs/'+result['id']+'/export').content
 with zipfile.ZipFile(io.BytesIO(payload)) as z:
  assert 'source-mission.json' in z.namelist() and 'implementation/clavius/repairs.py' in z.namelist()
  assert len([name for name in z.namelist() if name.startswith('scenarios/')])==4
  if diviner:assert {'context/diviner-manifest.json','context/diviner-connecting-ridge.json'}<=set(z.namelist())
 path=tmp_path/'repair.zip';path.write_bytes(payload)
 reproduced=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_simulation.py'),str(path)],capture_output=True,text=True,env=os.environ)
 assert reproduced.returncode==0,reproduced.stdout+reproduced.stderr
 assert json.loads(reproduced.stdout)['reproduced']
 # A child remains independently reproducible with its immutable association.
 child=result['baseline']['run_id'];path.write_bytes(client.get('/api/v1/runs/'+child+'/export').content)
 child_repro=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_simulation.py'),str(path)],capture_output=True,text=True,env=os.environ)
 assert child_repro.returncode==0,child_repro.stdout+child_repro.stderr


def test_cancelled_repair_keeps_checkpoint_without_a_completed_parent(monkeypatch):
 from clavius import api,store
 from clavius.mission import Cancelled
 robot_id=client.get('/api/v1/health').json()['reference_robot_id']
 source=complete(client.post('/api/v1/planning-runs',json={'robot_id':robot_id,'duration_hours':.02,'waypoints':[{'east_m':0,'north_m':0}],'activities':[]}).json()['id'])
 checkpoint={'kind':'synthetic_repair_checkpoint_fixture','search_state':'running_partial','candidates':[]}
 def stopped_search(request,robot,source,progress,cancel):
  progress(.1,'Synthetic checkpoint fixture',partial_result=checkpoint,partial_artifact_sha256=store.artifact(checkpoint))
  while not cancel():time.sleep(.01)
  raise Cancelled()
 monkeypatch.setattr(api,'repair_search',stopped_search)
 job=client.post('/api/v1/repair-searches',json={'source_run_id':source['result_id']}).json()
 for _ in range(100):
  if client.get('/api/v1/jobs/'+job['id']).json().get('partial_result'):break
  time.sleep(.01)
 client.post('/api/v1/jobs/'+job['id']+'/cancel')
 finished=complete(job['id']);assert finished['state']=='cancelled' and finished['result_id'] is None
 response=client.get('/api/v1/jobs/'+job['id']+'/partial-evidence')
 assert response.status_code==200 and response.json()['checkpoint']==checkpoint
