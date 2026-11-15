"""Seeded engineering sensitivity cases with published correlated terrain surfaces."""
import numpy as np
from pydantic import BaseModel,Field,model_validator
from .mission import MissionRequest,evaluate,Cancelled
from .terrain import TerrainRealization,site
from .provenance import implementation
from . import store
class SweepRequest(BaseModel):
 mission:MissionRequest
 samples:int=Field(default=6,ge=2,le=20)
 seed:int=Field(default=42,ge=0,le=2147483647)
 terrain_realization_ids:list[TerrainRealization]|None=Field(default=None,min_length=1,max_length=4)
 @model_validator(mode='after')
 def unique_surfaces(self):
  if self.terrain_realization_ids and len(set(self.terrain_realization_ids))!=len(self.terrain_realization_ids):raise ValueError('Choose each terrain realization once.')
  return self

def sweep(request,robot,progress=lambda *_:None,cancel=lambda:False):
 rng=np.random.default_rng(request.seed);terrain_rng=np.random.default_rng(np.random.SeedSequence([request.seed,0x54455252,1]));outcomes=[];evidence=None
 ids=request.terrain_realization_ids or list(dict.fromkeys([request.mission.scenario.terrain_realization_id,'nominal','pgda78-0001']))
 order=[]
 while len(order)<request.samples:order.extend(terrain_rng.permutation(ids).tolist())
 for i in range(request.samples):
  if cancel():raise Cancelled()
  scenario={'capacity_multiplier':float(rng.uniform(.7,1.)),'solar_multiplier':float(rng.uniform(.6,1.)),'mobility_multiplier':float(rng.uniform(1.,1.6)),'speed_multiplier':float(rng.uniform(.7,1.)),'terrain_error_sigma':0.,'terrain_realization_id':order[i],'soil':'assumed_firm'}
  try:
   mission=MissionRequest.model_validate({**request.mission.model_dump(),'scenario':scenario,'seed':(request.seed+i)%2147483648,'name':(request.mission.name[:80]+f' · scenario {i+1}')[:100]})
   result=evaluate(mission,robot,lambda p,m:progress((i+p)/request.samples,f'Scenario {i+1}/{request.samples} · {m}'),cancel)
   if evidence is None:evidence=result['provenance']
   artifact=store.artifact(result);saved=store.put('run',{**result,'artifact_sha256':artifact,'kind':'mission','scenario_sample':i+1})
   outcomes.append({'run_id':saved['id'],'scenario':scenario,'status':result['status'],'metrics':result['metrics'],'first_violation':result['first_violation'],'input_sha256':result['input_sha256']})
  except (ValueError,OSError) as error:
   outcomes.append({'run_id':None,'scenario':scenario,'status':'insufficient_evidence','metrics':{},'first_violation':None,'reason':str(error),'input_sha256':None})
   progress((i+1)/request.samples,f'Scenario {i+1}: insufficient scientific support retained')
 if evidence is None:evidence={'terrain':site(request.mission.site_id).manifest,'implementation':implementation(),'models':{'terrain':'pgda78-published-clones-v0.1'}}
 supported=[r['metrics'] for r in outcomes if r['metrics']];unknown=sum(r['status']=='insufficient_evidence' for r in outcomes);violations=sum(r['status']=='constraint_violated' for r in outcomes)
 return {'schema_version':'0.2.0','name':request.mission.name[:75]+' · uncertainty sweep','robot_id':robot['id'],'request':request.model_dump(),'status':'constraint_violated' if violations else ('insufficient_evidence' if unknown else 'supported_under_assumptions'),'assessment_scope':'bounded declared hardware assumptions and a predeclared subset of published statistical terrain surfaces; not calibrated mission risk or a complete terrain error distribution','metrics':{'samples':request.samples,'violating_scenarios':violations,'unsupported_scenarios':unknown,'minimum_battery_wh':min((r['minimum_battery_wh'] for r in supported),default=None),'distance_m':supported[0]['distance_m'] if supported else None,'distance_range_m':[min(r['distance_m'] for r in supported),max(r['distance_m'] for r in supported)] if supported else None},'outcomes':outcomes,'provenance':{**evidence,'seed':request.seed,'sampling':'Independent uniform engineering bounds; balanced seeded permutation of explicitly selected terrain surface IDs. No outcomes select the terrain pool.','bounds':{'capacity_multiplier':[.7,1.],'solar_multiplier':[.6,1.],'mobility_multiplier':[1.,1.6],'speed_multiplier':[.7,1.]},'terrain_ensemble':{'id':'published-clones-sweep-v0.1','allowed_ids':ids,'case_sequence':order[:request.samples],'terrain_rng':'NumPy SeedSequence [seed, 0x54455252, 1]','default_audit_reserved_ids':['pgda78-0002','pgda78-0003'],'limits':'Only three predeclared clones per site are loaded. Regional terrain stays nominal; this is not the complete 100-member distribution. A user-selected source clone can also appear in this testing pool.'}}}
