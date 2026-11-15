"""Bounded surface repair enumeration with frozen, independent audit scenarios."""
import itertools,hashlib,json
from datetime import datetime,timedelta
import numpy as np
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .mission import MissionRequest,evaluate,Cancelled
from .terrain import TerrainRealization
from .geometry import epoch,utc_from_et
from .provenance import implementation
from . import store

MODEL_ID='bounded-surface-repair-v0.2'
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Bounds(Strict):
 capacity_factor:tuple[float,float]=(.85,1.)
 solar_factor:tuple[float,float]=(.75,1.)
 mobility_factor:tuple[float,float]=(1.,1.25)
 speed_factor:tuple[float,float]=(.8,1.)
 start_delay_s:tuple[int,int]=(0,1800)
 initial_temperature_delta_c:tuple[float,float]=(-3.,3.)
 @model_validator(mode='after')
 def ordered(self):
  limits={'capacity_factor':(.5,1.),'solar_factor':(0,1.),'mobility_factor':(1.,2.),'speed_factor':(.5,1.),'start_delay_s':(0,7200),'initial_temperature_delta_c':(-20,20)}
  for key,(lower,upper) in limits.items():
   a,b=getattr(self,key)
   if not lower<=a<=b<=upper:raise ValueError(f'{key} must be ordered within [{lower}, {upper}].')
  return self
class Costs(Strict):
 date_day:float=Field(default=1,ge=0,le=100)
 wait_hour:float=Field(default=2,ge=0,le=100)
 capacity_percent:float=Field(default=.25,ge=0,le=100)
 solar_percent:float=Field(default=.25,ge=0,le=100)
 heater_toggle:float=Field(default=5,ge=0,le=100)
class RepairSearchRequest(Strict):
 source_run_id:str=Field(pattern=r'^[0-9a-f-]{36}$')
 date_offsets_days:list[int]=Field(default_factory=lambda:[-14,-7,-1,0,1,7,14],min_length=1,max_length=15)
 wait_at_start_s:list[float]=Field(default_factory=lambda:[0.],min_length=1,max_length=3)
 capacity_factors:list[float]=Field(default_factory=lambda:[1.],min_length=1,max_length=3)
 solar_factors:list[float]=Field(default_factory=lambda:[1.],min_length=1,max_length=3)
 heater_choices:list[bool]|None=Field(default=None,min_length=1,max_length=2)
 max_candidates:int=Field(default=12,ge=1,le=24)
 max_audit_candidates:int=Field(default=3,ge=1,le=6)
 audit_samples:int=Field(default=3,ge=1,le=8)
 audit_seed:int=Field(default=53142,ge=0,le=2147483647)
 audit_bounds:Bounds=Field(default_factory=Bounds)
 audit_terrain_realization_ids:list[TerrainRealization]|None=Field(default=None,min_length=1,max_length=3)
 costs:Costs=Field(default_factory=Costs)
 @model_validator(mode='after')
 def bounded(self):
  for key,lo,hi in [('date_offsets_days',-28,28),('wait_at_start_s',0,7200),('capacity_factors',1,1.2),('solar_factors',1,1.2)]:
   if any(not lo<=v<=hi for v in getattr(self,key)):raise ValueError(f'{key} must stay in [{lo}, {hi}].')
  if self.audit_terrain_realization_ids and len(set(self.audit_terrain_realization_ids))!=len(self.audit_terrain_realization_ids):raise ValueError('Audit terrain IDs must be distinct.')
  return self

def digest(value):return hashlib.sha256(store.canonical(value)).hexdigest()
def required_signature(mission):
 return digest({'robot_id':mission.robot_id,'site_id':mission.site_id,'waypoints':[p.model_dump() for p in mission.waypoints],'required_activities':[a.model_dump() for a in mission.activities],'duration_hours':mission.duration_hours,'max_earth_outage_s':mission.max_earth_outage_s,'observer_height_m':mission.observer_height_m})
def proposal(base,patch):
 value=base.model_dump();value['start_utc']=(datetime.fromisoformat(base.start_utc.replace('Z','+00:00'))+timedelta(days=patch['date_offset_days'])).isoformat()
 value['scenario']['capacity_multiplier']*=patch['capacity_factor'];value['scenario']['solar_multiplier']*=patch['solar_factor'];value['heater_enabled']=patch['heater_enabled']
 if patch['wait_at_start_s']:
  value['activities'].insert(0,{'kind':'wait','waypoint':0,'duration_s':patch['wait_at_start_s']})
 value['name']=(base.name[:55]+' · repair '+patch['id'][:6])[:100]
 result=MissionRequest(**value)
 original=[a.model_dump() for a in base.activities];added=1 if patch['wait_at_start_s'] else 0
 if [a.model_dump() for a in result.activities][added:]!=original:raise ValueError('Repair changed a required activity.')
 if result.waypoints!=base.waypoints or result.robot_id!=base.robot_id:raise ValueError('Repair changed protected route/robot inputs.')
 return result

def candidates(request,base):
 if request.heater_choices is not None and any(h!=base.heater_enabled for h in request.heater_choices) and base.thermal is None:raise ValueError('Enable thermal screening in the source mission before permitting heater changes.')
 baseline={'date_offset_days':0,'wait_at_start_s':0.,'capacity_factor':1.,'solar_factor':1.,'heater_enabled':base.heater_enabled}
 values=[baseline]+[dict(zip(baseline,values)) for values in itertools.product(request.date_offsets_days,request.wait_at_start_s,request.capacity_factors,request.solar_factors,request.heater_choices or [base.heater_enabled])]
 unique={}
 for patch in values:
  identity=digest(patch);costs={'date':abs(patch['date_offset_days'])*request.costs.date_day,'wait':patch['wait_at_start_s']/3600*request.costs.wait_hour,'capacity':100*(patch['capacity_factor']-1)*request.costs.capacity_percent,'solar':100*(patch['solar_factor']-1)*request.costs.solar_percent,'heater':int(patch['heater_enabled']!=base.heater_enabled)*request.costs.heater_toggle}
  unique[identity]={**patch,'id':identity,'cost':sum(costs.values()),'cost_components':costs,'is_baseline':patch==baseline}
 return sorted(unique.values(),key=lambda p:(not p['is_baseline'],p['cost'],p['id']))

def audit_cases(request,base=None):
 # Dedicated namespace; independent of the existing scenario-search RNG stream.
 rng=np.random.default_rng(np.random.SeedSequence([request.audit_seed,0x52455041,1]));cases=[]
 source_id=base.scenario.terrain_realization_id if base else 'nominal'
 ids=request.audit_terrain_realization_ids or [r for r in ['pgda78-0002','pgda78-0003'] if r!=source_id]
 if source_id in ids:raise ValueError('Audit terrain must be distinct from the surface used for nominal candidate selection.')
 terrain_rng=np.random.default_rng(np.random.SeedSequence([request.audit_seed,0x54455252,2]));order=[]
 while len(order)<request.audit_samples:order.extend(terrain_rng.permutation(ids).tolist())
 for i in range(request.audit_samples):
  case={'index':i+1,'terrain_realization_id':order[i]}
  for key in ['capacity_factor','solar_factor','mobility_factor','speed_factor','initial_temperature_delta_c']:
   a,b=getattr(request.audit_bounds,key);case[key]=float(rng.uniform(a,b)) if a!=b else float(a)
  a,b=request.audit_bounds.start_delay_s;case['start_delay_s']=int(rng.integers(a,b+1));cases.append(case)
 return cases

def audit_request(candidate,case):
 value=candidate.model_dump();value['scenario']['terrain_realization_id']=case['terrain_realization_id'];value['start_utc']=utc_from_et(epoch(candidate.start_utc)+case['start_delay_s'])
 for key,field in [('capacity_factor','capacity_multiplier'),('solar_factor','solar_multiplier'),('mobility_factor','mobility_multiplier'),('speed_factor','speed_multiplier')]:value['scenario'][field]*=case[key]
 if value['thermal']:value['thermal']['initial_temperature_c']+=case['initial_temperature_delta_c']
 value['name']=(candidate.name[:78]+f' · audit {case["index"]}')[:100]
 # No clamping: an audit outside the supported model domain remains unknown.
 return MissionRequest(**value)

def summary(result,saved):return {'run_id':saved['id'],'input_sha256':result['input_sha256'],'status':result['status'],'metrics':result['metrics'],'first_violation':result['first_violation']}
def margins(result):
 m=result['metrics'];r=result['request'];values={'battery_reserve_wh':m['minimum_battery_wh']-m['reserve_wh'],'deadline_s':r['duration_hours']*3600-m['scheduled_completion_s'],'earth_outage_s':r['max_earth_outage_s']-m['longest_earth_outage_s']}
 if r.get('thermal'):values.update(cold_temperature_c=m['minimum_battery_temperature_c']-r['thermal']['operating_min_c'],hot_temperature_c=r['thermal']['operating_max_c']-m['maximum_battery_temperature_c'])
 return values

def search(request,robot,source,progress=lambda *_args,**_kwargs:None,cancel=lambda:False):
 if source.get('kind')!='mission' or source.get('id')!=request.source_run_id or source['robot_id']!=robot['id']:raise ValueError('Repair search requires a saved mission for this exact robot version.')
 if source.get('robot_profile_sha256') and source['robot_profile_sha256']!=robot['profile_sha256']:raise ValueError('The source capability profile differs from the selected robot version.')
 base=MissionRequest(**source['request']);space=candidates(request,base);cases=audit_cases(request,base);outcomes=[];frozen=[];simulations=0;baseline=None;evidence=None
 protected=required_signature(base);code=implementation();audit_hash=digest(cases);planned=min(len(space),request.max_candidates)+request.max_audit_candidates*request.audit_samples
 def report(state):
  verified=[p for p in outcomes if (p.get('audit') or {}).get('supported_all_cases')]
  verified.sort(key=lambda p:(p['cost'],p['id']));budget=len(space)>request.max_candidates
  coverage_state='candidate_budget_exhausted' if state=='complete' and budget else state
  return {'schema_version':'0.2.0','name':base.name[:65]+' · bounded repair search','robot_id':robot['id'],'request':request.model_dump(),'search_state':coverage_state,'status':'verified_repair_found' if verified else ('incomplete_search' if state!='complete' else 'no_repair_found_in_search'),'assessment_scope':'Bounded surface input alternatives, fixed required route/activities and independent declared-assumption audits. No global optimum, physical mission certification or failure probability.','source_mission':{'id':source['id'],'artifact_sha256':source['artifact_sha256'],'input_sha256':source['input_sha256'],'recorded_first_violation':source.get('first_violation'),'policy':'Source request is rerun under the current recorded implementation before alternatives are compared.'},'baseline':baseline,'candidates':outcomes,'recommended_candidate_id':verified[0]['id'] if verified else None,'metrics':{'candidate_space_size':len(space),'nominal_checked':len(outcomes),'nominal_supported':sum(p.get('nominal',{}).get('status')=='supported_under_assumptions' for p in outcomes),'audit_candidates_frozen':len(frozen),'audit_cases_per_candidate':len(cases),'verified_candidates':len(verified),'simulation_evaluations':simulations,'unsearched_candidates':max(0,len(space)-len(outcomes)),'candidate_budget_exhausted':budget and len(outcomes)>=request.max_candidates,'search_complete':state=='complete' and not budget,'requested_work_complete':state=='complete'},'selection_policy':{'label':'Smallest verified repair found within the evaluated candidate and audit budgets.','cost_formula':request.costs.model_dump(),'cost_units':'User-weighted score: absolute UTC calendar days; hours of added wait; percent capacity/solar scenario gain; heater toggle.','audit_selection':'Freeze the lowest-cost nominally supported candidates before viewing any audit outcomes. Use identical independently generated audit perturbations across the frozen candidates.','not_audited_nominal_candidates':max(0,sum(p.get('nominal',{}).get('status')=='supported_under_assumptions' for p in outcomes)-len(frozen))},'preserved_requirements':{'signature':protected,'robot_id':base.robot_id,'site_id':base.site_id,'required_activities':[a.model_dump() for a in base.activities],'waypoints':[p.model_dump() for p in base.waypoints],'duration_hours':base.duration_hours,'max_earth_outage_s':base.max_earth_outage_s},'audit_cases':cases,'audit_cases_sha256':audit_hash,'limitations':['Only date, initial wait, usable-capacity/solar scenario multipliers and explicitly allowed thermostat changes are searched. No second site, route generation or arbitrary hardware redesign.','Capacity/solar gains are declared scenarios; mass, mechanical geometry and thermal properties are not redesigned.','A predeclared subset of published correlated terrain surfaces is audited. Regional uncertainty, calibrated soil/dust distributions and radio-link budgets remain unmodeled.','Audit draws are engineering sensitivity cases, not measured lunar distributions or estimated real-world failure probabilities.','Required activities remain fixed; extra waiting consumes the same declared mission duration.'],'provenance':{**(evidence or {}),'implementation':code,'models':{**((evidence or {}).get('models',{})),'repair':MODEL_ID},'audit_rng':'Hardware: SeedSequence [audit_seed, 0x52455041, 1]; terrain: [audit_seed, 0x54455252, 2]. Audit surfaces differ from the nominal candidate surface; no audit outcome selects candidates.'},'input_sha256':digest({'request':request.model_dump(),'source_artifact_sha256':source['artifact_sha256'],'robot_profile_sha256':robot['profile_sha256'],'audit_cases_sha256':audit_hash,'required_signature':protected,'baseline_input_sha256':baseline.get('input_sha256') if baseline else None,'source_provenance':evidence,'implementation':code})}
 def checkpoint(message):
  partial=report('running_partial');progress(min(.96,simulations/max(1,planned)),message,partial_result=partial,partial_artifact_sha256=store.artifact(partial))
 def execute(mission,label):
  nonlocal simulations,evidence
  if cancel():raise Cancelled()
  result=evaluate(mission,robot,lambda p,m:progress(min(.96,(simulations+p)/max(1,planned)),label+' · '+m),cancel)
  if evidence is None:evidence=result['provenance']
  result['repair_source_run_id']=source['id']
  artifact=store.artifact(result);saved=store.put('run',{**result,'artifact_sha256':artifact,'kind':'mission'})
  simulations+=1;value=summary(result,saved);value['margins']=margins(result);return result,value
 for index,patch in enumerate(space[:request.max_candidates]):
  if cancel():raise Cancelled()
  value={**patch,'audit':None}
  try:
   mission=base if patch['is_baseline'] else proposal(base,patch)
   result,nominal=execute(mission,f'Candidate {index+1}/{min(len(space),request.max_candidates)}')
   value['nominal']=nominal;value['candidate_request']=mission.model_dump()
   if patch['is_baseline']:baseline={**nominal,'provenance':result['provenance'],'recorded_status':source['status'],'current_status':result['status']}
  except (ValueError,OSError) as error:
   value['nominal']={'run_id':None,'status':'insufficient_evidence','reason':str(error),'metrics':{},'first_violation':None}
   if patch['is_baseline']:baseline={**value['nominal'],'recorded_status':source['status'],'current_status':'insufficient_evidence'}
  outcomes.append(value);checkpoint(f'Checked {index+1} nominal candidates; audit set remains unused')
 supported=sorted([p for p in outcomes if p['nominal']['status']=='supported_under_assumptions'],key=lambda p:(p['cost'],p['id']))
 frozen=[p['id'] for p in supported[:request.max_audit_candidates]];checkpoint('Nominal selection frozen; evaluating independent audit cases')
 for value in supported[:request.max_audit_candidates]:
  audit=[];value['audit']={'cases':audit,'supported_all_cases':False,'completed':False}
  for case in cases:
   if cancel():raise Cancelled()
   try:
    mission=audit_request(MissionRequest(**value['candidate_request']),case)
    _,outcome=execute(mission,f'Auditing candidate {value["id"][:6]} · case {case["index"]}/{len(cases)}')
   except (ValueError,OSError) as error:outcome={'run_id':None,'status':'insufficient_evidence','reason':str(error),'metrics':{},'first_violation':None}
   audit.append({'case_index':case['index'],**outcome});checkpoint('Retained completed audit evidence')
  value['audit']['completed']=True;value['audit']['supported_all_cases']=all(a['status']=='supported_under_assumptions' for a in audit);checkpoint('Completed frozen candidate audit')
 return report('complete')
