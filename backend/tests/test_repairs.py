"""Repair-policy invariants, disjoint audit selection, and real-site replay."""
import copy,json
import pytest
from clavius import repairs,store
from clavius.repairs import RepairSearchRequest,Bounds,candidates,proposal,audit_cases,search
from clavius.mission import MissionRequest,evaluate,Cancelled
from clavius.thermal import ThermalConfig
from clavius.robots import import_robot
from clavius.paths import ROOT

@pytest.fixture
def rover():return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))
def saved_source(request,robot):
 result=evaluate(request,robot);return store.put('run',{**result,'artifact_sha256':store.artifact(result),'kind':'mission'})

def test_proposals_preserve_required_tasks_route_robot_and_limits(rover):
 base=MissionRequest(robot_id=rover['id']);before=base.model_dump()
 request=RepairSearchRequest(source_run_id='0'*36,date_offsets_days=[-1,0,1],wait_at_start_s=[0,3600],capacity_factors=[1,1.2],solar_factors=[1,1.1])
 for patch in candidates(request,base):
  result=proposal(base,patch);offset=1 if patch['wait_at_start_s'] else 0
  assert result.activities[offset:]==base.activities
  assert result.robot_id==base.robot_id and result.waypoints==base.waypoints
  assert result.duration_hours==base.duration_hours and result.max_earth_outage_s==base.max_earth_outage_s
 assert base.model_dump()==before


def test_repair_bounds_and_unmodeled_heater_toggle_are_rejected():
 for change in [{'date_offsets_days':[29]},{'capacity_factors':[1.3]},{'wait_at_start_s':[-1]},{'max_candidates':25},{'audit_bounds':{'capacity_factor':[1,.8]}},{'costs':{'date_day':float('nan')}}]:
  with pytest.raises(ValueError):RepairSearchRequest(source_run_id='0'*36,**change)
 req=RepairSearchRequest(source_run_id='0'*36,heater_choices=[False,True])
 with pytest.raises(ValueError,match='thermal'):candidates(req,MissionRequest(robot_id='test'))
 assert len(candidates(req,MissionRequest(robot_id='test',thermal=ThermalConfig())))>=2


def test_audit_inputs_are_repeatable_and_use_a_dedicated_seed_stream():
 request=RepairSearchRequest(source_run_id='0'*36)
 a=audit_cases(request);b=audit_cases(request);c=audit_cases(request.model_copy(update={'audit_seed':request.audit_seed+1}))
 assert a==b and a!=c
 assert all(.85<=x['capacity_factor']<=1 and 0<=x['start_delay_s']<=1800 for x in a)


def synthetic(request,robot,*args):
 """Explicit synthetic branch fixture; no NASA label or trajectory is asserted."""
 audit=' · audit ' in request.name
 supported='2028-01-01' in request.start_utc or ('2028-01-02' in request.start_utc and not audit)
 return {'request':request.model_dump(),'status':'supported_under_assumptions' if supported else 'constraint_violated','input_sha256':repairs.digest(request.model_dump()),'first_violation':None if supported else {'code':'CONTACT_OUTAGE_LIMIT','t_s':21600,'message':'Synthetic outage case','severity':'violation'},'metrics':{'minimum_battery_wh':200.,'reserve_wh':75.,'scheduled_completion_s':60.,'longest_earth_outage_s':0. if supported else 43200.},'provenance':{'models':{'environment':'synthetic_policy_test'},'terrain':{'source_class':'synthetic_fixture'}}}

def test_nominal_selection_is_frozen_before_audit_and_failed_audit_is_not_recommended(monkeypatch):
 base=MissionRequest(robot_id='fixture',start_utc='2028-01-14T00:00:00Z');source={'id':'0'*36,'kind':'mission','robot_id':'fixture','request':base.model_dump(),'artifact_sha256':'fixture-source','input_sha256':'fixture-input','status':'constraint_violated'}
 monkeypatch.setattr(repairs,'evaluate',synthetic);checkpoints=[]
 request=RepairSearchRequest(source_run_id=source['id'],date_offsets_days=[-13,-12,0],max_audit_candidates=2,audit_samples=2)
 result=search(request,{'id':'fixture','profile_sha256':'fixture'},source,lambda *a,**kw:checkpoints.append(copy.deepcopy(kw['partial_result'])) if 'partial_result' in kw else None)
 selected=next(p for p in result['candidates'] if p['id']==result['recommended_candidate_id'])
 assert selected['date_offset_days']==-13 and selected['audit']['supported_all_cases']
 cheaper=next(p for p in result['candidates'] if p['date_offset_days']==-12)
 assert cheaper['cost']<selected['cost'] and not cheaper['audit']['supported_all_cases']
 first_audit=next(c for c in checkpoints if any(p.get('audit') for p in c['candidates']))
 assert first_audit['metrics']['nominal_checked']==3 and first_audit['metrics']['audit_candidates_frozen']==2
 assert result['metrics']['simulation_evaluations']==7
 assert result['status']=='verified_repair_found'


def test_budget_exhaustion_and_cancelled_checkpoint_do_not_claim_completed_search(monkeypatch):
 base=MissionRequest(robot_id='fixture');source={'id':'0'*36,'kind':'mission','robot_id':'fixture','request':base.model_dump(),'artifact_sha256':'fixture-source','input_sha256':'fixture-input','status':'constraint_violated'}
 monkeypatch.setattr(repairs,'evaluate',synthetic)
 req=RepairSearchRequest(source_run_id=source['id'],max_candidates=1,audit_samples=1,max_audit_candidates=1)
 result=search(req,{'id':'fixture','profile_sha256':'fixture'},source)
 assert result['metrics']['candidate_budget_exhausted'] and result['metrics']['unsearched_candidates']>0
 assert result['search_state']=='candidate_budget_exhausted' and not result['metrics']['search_complete']
 assert result['metrics']['requested_work_complete']
 checkpoints=[]
 def progress(*args,**kw):
  if 'partial_result' in kw:checkpoints.append(kw['partial_result'])
 with pytest.raises(Cancelled):search(req,{'id':'fixture','profile_sha256':'fixture'},source,progress,lambda:bool(checkpoints))
 assert checkpoints[-1]['search_state']=='running_partial'
 assert not checkpoints[-1]['metrics']['search_complete']


def test_real_site_failed_mission_is_repaired_without_removing_science(rover):
 mission=MissionRequest(robot_id=rover['id'],start_utc='2028-01-14T00:00:00Z',duration_hours=.1,max_earth_outage_s=120,waypoints=[{'east_m':0,'north_m':0}],activities=[{'kind':'science','waypoint':0,'duration_s':60}])
 source=saved_source(mission,rover)
 request=RepairSearchRequest(source_run_id=source['id'],date_offsets_days=[-13,0],max_candidates=2,max_audit_candidates=1,audit_samples=2)
 result=search(request,rover,source)
 assert result['baseline']['first_violation']['code']=='CONTACT_OUTAGE_LIMIT'
 selected=next(p for p in result['candidates'] if p['id']==result['recommended_candidate_id'])
 assert selected['date_offset_days']==-13 and selected['audit']['supported_all_cases']
 assert selected['candidate_request']['activities']==mission.model_dump()['activities']
 assert all(store.get(a['run_id'])['request']['activities']==mission.model_dump()['activities'] for a in selected['audit']['cases'])


def test_audit_outside_model_domain_is_not_clamped_or_marked_supported(monkeypatch):
 base=MissionRequest(robot_id='fixture',start_utc='2028-01-01T00:00:00Z',scenario={'speed_multiplier':.2});source={'id':'0'*36,'kind':'mission','robot_id':'fixture','request':base.model_dump(),'artifact_sha256':'fixture-source','input_sha256':'fixture-input','status':'supported_under_assumptions'}
 monkeypatch.setattr(repairs,'evaluate',synthetic)
 result=search(RepairSearchRequest(source_run_id=source['id'],date_offsets_days=[0],audit_samples=1),{'id':'fixture','profile_sha256':'fixture'},source)
 assert result['recommended_candidate_id'] is None
 case=result['candidates'][0]['audit']['cases'][0]
 assert case['status']=='insufficient_evidence' and case['run_id'] is None

def test_thermal_repair_enables_heater_and_survives_fresh_cases(rover):
 mission=MissionRequest(robot_id=rover['id'],duration_hours=.5,waypoints=[{'east_m':0,'north_m':0}],activities=[{'kind':'science','waypoint':0,'duration_s':60}],heater_enabled=False,thermal=ThermalConfig(initial_temperature_c=1,heat_capacity_j_k=200))
 source=saved_source(mission,rover)
 assert source['first_violation']['code']=='BATTERY_TOO_COLD'
 request=RepairSearchRequest(source_run_id=source['id'],date_offsets_days=[0],heater_choices=[False,True],max_candidates=2,max_audit_candidates=1,audit_samples=2)
 result=search(request,rover,source)
 selected=next(p for p in result['candidates'] if p['id']==result['recommended_candidate_id'])
 assert selected['heater_enabled'] and selected['audit']['supported_all_cases']
 assert selected['nominal']['metrics']['minimum_battery_temperature_c']>=-1e-6
 assert selected['candidate_request']['activities']==mission.model_dump()['activities']
