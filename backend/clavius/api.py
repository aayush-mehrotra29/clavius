"""Local simulation API; numerical work runs outside request handlers."""
import concurrent.futures,hashlib,io,json,mimetypes,shutil,threading,traceback,zipfile
from pathlib import Path
from fastapi import FastAPI,File,UploadFile,Form,HTTPException,Query
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field
from .paths import ROOT,DATA,RUNTIME
from . import store
from .robots import import_robot,validate_profile,ImportIssue,parse_urdf
from .mission import MissionRequest,evaluate,Cancelled,pose_at
from .terrain import site,TerrainCoverageError,catalogue,definition,dependencies,TerrainRealization,realization_catalogue
from .gazebo_client import GazeboClient
from .thermal import ThermalConfig,MODEL_ID,REFERENCE

app=FastAPI(title='Clavius lunar simulation',version='0.2.0')
pool=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='clavius')
cancellations={}

def public_robot(robot):return robot

def initialize_reference():
 profile=json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text())
 raw=(ROOT/'public/robots/clavius-r1.zip').read_bytes()
 robot=import_robot(raw,'clavius-r1.zip',profile)
 robot['source_class']='hypothetical_reference';store.put('robot',robot,robot['id'])
 return robot
reference=initialize_reference()
for job in store.listing('job'):
 if job.get('state') in {'queued','running'}:store.put('job',{**job,'state':'failed','error':'Backend restarted before this job completed.'},job['id'])

@app.get('/api/v1/health')
def health():
 import importlib.metadata
 from .integrity import verify_sources
 try:
  verify_sources('terrain',dependencies(definition('connecting-ridge')));verify_sources('kernels');ready=True;error=None
 except (ValueError,OSError) as e:ready=False;error=str(e)
 engines=physics_engines()
 return {'status':'ready' if ready else 'missing_inputs','version':'0.2.0','engines':{'mujoco':importlib.metadata.version('mujoco'),'gazebo':engines['gazebo']['available']},'physics_engines':engines,'terrain_ready':ready,'input_error':error,'reference_robot_id':reference['id']}

@app.get('/api/v1/physics-engines')
def physics_engines():
 import importlib.metadata
 return {'mujoco':{'available':True,'name':'MuJoCo','version':importlib.metadata.version('mujoco'),'location':'local'},'gazebo':GazeboClient().capabilities()}

@app.get('/api/v1/thermal-model')
def thermal_model():
 return {'id':MODEL_ID,'defaults':ThermalConfig().model_dump(),'schema':ThermalConfig.model_json_schema(),'source_class':'declared_engineering_scenario','reference':REFERENCE,'description':'One uniform battery/enclosure node with radiation, ground conduction, solar/internal heat, thermostat and charging inhibition. Defaults are hypothetical engineering assumptions, not measured rover properties or Diviner temperatures.'}

@app.post('/api/v1/thermal-model/validate')
def validate_thermal_model(config:ThermalConfig):
 try:
  from .diviner import resolve_boundary
  resolve_boundary(config)
 except (ValueError,OSError) as e:raise HTTPException(422,str(e)) from e
 return config.model_dump()

@app.get('/api/v1/sites/{identity}/drive-environment')
def drive_environment(identity:str,start_utc:str,elapsed_s:float=Query(0,ge=0,allow_inf_nan=False),
                      east_m:float=Query(0,allow_inf_nan=False),north_m:float=Query(0,allow_inf_nan=False)):
 from .drive_environment import live_sample
 if not any(d['id']==identity for d in catalogue()):raise HTTPException(404,'Unknown drive site.')
 try:return live_sample(identity,start_utc,elapsed_s,east_m,north_m)
 except (ValueError,OSError) as e:raise HTTPException(422,str(e)) from e

@app.get('/api/v1/sites/{identity}/thermal-context')
def thermal_context(identity:str,east_m:float=0,north_m:float=0):
 if not any(d['id']==identity for d in catalogue()):raise HTTPException(404)
 try:
  from .diviner import sample
  if not all(__import__('math').isfinite(v) for v in [east_m,north_m]):raise ValueError('Context coordinates must be finite ENU metres.')
  point=site(identity).sample(east_m,north_m)
  if not bool(point['covered']):raise ValueError('Point is outside the prepared local terrain.')
  return {**sample(float(point['lat_deg']),float(point['lon_deg']),site_id=identity),'site_id':identity,'east_m':east_m,'north_m':north_m}
 except (ValueError,OSError) as e:return {'available':False,'reason':str(e)}

@app.get('/api/v1/robots')
def robots():return store.listing('robot')

@app.get('/api/v1/robots/{identity}')
def robot(identity:str):
 result=store.get(identity)
 if not result or 'model' not in result:raise HTTPException(404,'Robot not found.')
 return result

@app.post('/api/v1/robots')
async def upload_robot(package:UploadFile=File(...),profile_json:str|None=Form(None)):
 raw=await package.read(30*1024*1024+1)
 try:
  profile=json.loads(profile_json) if profile_json else None
  if profile is None:
   _,files=parse_urdf(raw,package.filename or '')
   sidecars=[v for n,v in files.items() if n.endswith('clavius-profile.json')]
   if len(sidecars)==1:profile=json.loads(sidecars[0])
  return import_robot(raw,package.filename or '',profile)
 except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e)) from e

@app.put('/api/v1/robots/{identity}/profile')
def edit_profile(identity:str,profile:dict):
 current=robot(identity)
 try:
  validate_profile(profile)
  if abs(profile['mass_kg']-current['model']['mass_kg'])>max(.001,.01*current['model']['mass_kg']):raise ImportIssue('Profile mass differs from the imported URDF. Reconcile them before saving.')
  if current['model']['center_of_mass_body_m'] is not None and __import__('numpy').linalg.norm(__import__('numpy').array(profile['center_of_mass_body_m'])-current['model']['center_of_mass_body_m'])>.01:raise ImportIssue('Profile center of mass differs from the imported URDF. Edit mechanics to change the modeled center of mass.')
 except (ValueError,TypeError) as e:raise HTTPException(422,str(e)) from e
 h=store.artifact(profile);new_id=hashlib.sha256((current['package_sha256']+h).encode()).hexdigest()[:24]
 return store.put('robot',{**current,'name':profile['name'],'profile':profile,'profile_sha256':h,'parent_robot_id':identity},new_id)

@app.get('/api/v1/robot-assets/{package_hash}/{asset_path:path}')
def robot_asset(package_hash:str,asset_path:str):
 if len(package_hash)!=64 or any(c not in '0123456789abcdef' for c in package_hash):raise HTTPException(404)
 root=(RUNTIME/'robots'/package_hash).resolve();target=(root/asset_path).resolve()
 if not target.is_relative_to(root) or not target.is_file():raise HTTPException(404)
 return FileResponse(target)

@app.get('/api/v1/sites')
def sites():
 results=[]
 for entry in catalogue():
  try:terrain=site(entry['id']);manifest=terrain.manifest;available=True;reason=None
  except (ValueError,OSError) as error:manifest=None;available=False;reason=str(error)
  results.append({'id':entry['id'],'name':entry['name'],'latitude_deg':entry['latitude_deg'],'longitude_deg':entry['longitude_deg'],'native_resolution_m':5,'available':available,'reason':reason,'frame':'MOON_ME_DE421 / local ENU','source_manifest':manifest,'origin_selection':entry['origin_selection'],'terrain_realizations':[{'id':'nominal','label':'Nominal LOLA surface'},*[{k:r[k] for k in ['id','label']} for r in realization_catalogue(entry)]],'limits':['Sub-5 m hazards remain unresolved.','Posting is not wheel-scale hazard accuracy; source pixels include interpolation between LOLA tracks.']})
 return results

@app.get('/api/v1/sites/{identity}/terrain')
def terrain(identity:str,east_m:float=0,north_m:float=0,size_m:int=640,realization:TerrainRealization='nominal'):
 if not any(d['id']==identity for d in catalogue()):raise HTTPException(404)
 if size_m<40 or size_m>2000:raise HTTPException(422,'Terrain patch must span 40–2000 m.')
 try:return site(identity,realization).patch(east_m,north_m,size_m,5)
 except (ValueError,OSError) as e:raise HTTPException(422,str(e)) from e

@app.get('/api/v1/sites/{identity}/sample')
def sample(identity:str,east_m:float=0,north_m:float=0,realization:TerrainRealization='nominal'):
 import numpy as np
 if not any(d['id']==identity for d in catalogue()):raise HTTPException(404)
 value=site(identity,realization).sample(east_m,north_m)
 if not value['covered']:raise HTTPException(422,'No local terrain coverage at this point.')
 return {**{k:bool(v) if isinstance(v,(np.bool_,bool)) else (float(v) if np.isfinite(v) else None) for k,v in value.items()},'terrain_realization_id':realization}

def submit(kind,request,worker):
 if sum(j['state'] in {'queued','running'} for j in store.listing('job'))>=6:raise HTTPException(429,'Six jobs are already queued or running.')
 job=store.put('job',{'kind':kind,'state':'queued','progress':0.,'message':'Queued','request':request,'result_id':None});event=threading.Event();cancellations[job['id']]=event
 def work():
  def update(progress,message,**metadata):
   if event.is_set():raise Cancelled()
   store.put('job',{**store.get(job['id']),'state':'running','progress':progress,'message':message,**metadata},job['id'])
  try:
   update(.01,'Preparing inputs');result=worker(update,event.is_set)
   if event.is_set():raise Cancelled()
   h=store.artifact(result);saved=store.put('run',{**result,'artifact_sha256':h,'kind':kind})
   store.put('job',{**store.get(job['id']),'state':'completed','progress':1.,'message':'Complete','result_id':saved['id']},job['id'])
  except Cancelled:store.put('job',{**store.get(job['id']),'state':'cancelled','message':'Cancelled'},job['id'])
  except Exception as e:
   traceback.print_exc();store.put('job',{**store.get(job['id']),'state':'failed','message':str(e),'error':type(e).__name__},job['id'])
  finally:cancellations.pop(job['id'],None)
 pool.submit(work);return job

@app.post('/api/v1/planning-runs')
def planning_run(request:MissionRequest):
 model=robot(request.robot_id)
 if not model.get('profile'):raise HTTPException(422,'Robot needs a validated capability profile.')
 return submit('mission',request.model_dump(),lambda progress,cancel:evaluate(request,model,progress,cancel))

@app.get('/api/v1/jobs')
def list_jobs():return store.listing('job')

@app.get('/api/v1/jobs/{identity}')
def get_job(identity:str):
 result=store.get(identity)
 if not result or 'state' not in result:raise HTTPException(404)
 return result

@app.post('/api/v1/jobs/{identity}/cancel')
def cancel_job(identity:str):
 result=get_job(identity)
 if identity in cancellations:cancellations[identity].set()
 return get_job(identity)

@app.get('/api/v1/jobs/{identity}/partial-evidence')
def partial_job_evidence(identity:str):
 job=get_job(identity)
 if job.get('kind')!='repair' or not job.get('partial_result'):raise HTTPException(404,'No repair checkpoint has been retained yet.')
 partial=job['partial_result'];raw=store.canonical(partial)
 if hashlib.sha256(raw).hexdigest()!=job['partial_artifact_sha256']:raise HTTPException(503,'Repair checkpoint identity differs.')
 return Response(json.dumps({'job_id':identity,'job_state':job['state'],'checkpoint_sha256':job['partial_artifact_sha256'],'checkpoint':partial,'policy':'Partial search evidence. Completed child missions can be exported separately; this is not an accepted completed repair search.'},indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="clavius-partial-{identity}.json"'})

@app.get('/api/v1/runs')
def runs():
 return [{k:v for k,v in r.items() if k not in {'timeline','provenance','phases','trace'}} for r in store.listing('run')]

@app.get('/api/v1/runs/{identity}')
def run(identity:str):
 result=store.get(identity)
 if not result or 'artifact_sha256' not in result:raise HTTPException(404)
 return result

@app.get('/api/v1/runs/{identity}/export')
def export(identity:str):
 result=run(identity);raw=io.BytesIO()
 with zipfile.ZipFile(raw,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('assessment.json',json.dumps(result,indent=2,allow_nan=False))
  context=result.get('provenance',{}).get('diviner')
  if context:
   context_hash=context['derivative']['sha256'];captured=RUNTIME/'artifacts'/(context_hash+'.json')
   if not captured.is_file() or hashlib.sha256(captured.read_bytes()).hexdigest()!=context_hash:raise HTTPException(503,'Recorded Diviner context artifact is missing or altered.')
   z.write(captured,'context/diviner-'+context.get('selected_site_id','connecting-ridge')+'.json')
   z.writestr('context/diviner-manifest.json',json.dumps(context,indent=2,allow_nan=False))
  code_hash=result.get('provenance',{}).get('implementation',{}).get('source_sha256')
  snapshot=RUNTIME/'implementations'/str(code_hash)
  if snapshot.is_dir():
   for source in snapshot.rglob('*'):
    if source.is_file() and source.suffix in {'.py','.txt'}:z.write(source,'implementation/'+str(source.relative_to(snapshot)))
  if result.get('robot_id'):
   model=robot(result['robot_id']);z.writestr('robot.json',json.dumps(model,indent=2))
   root=RUNTIME/'robots'/model['package_sha256']
   for path in root.rglob('*'):
    if path.is_file():z.write(path,'robot-package/'+str(path.relative_to(root)))
  child_ids={o['run_id'] for o in result.get('outcomes',[]) if o.get('run_id')}
  for candidate in result.get('candidates',[]):
   nominal=candidate.get('nominal',{})
   if nominal.get('run_id'):child_ids.add(nominal['run_id'])
   child_ids.update(o['run_id'] for o in (candidate.get('audit') or {}).get('cases',[]) if o.get('run_id'))
  for child_id in sorted(child_ids):z.writestr('scenarios/'+child_id+'.json',json.dumps(run(child_id),indent=2,allow_nan=False))
  if result.get('kind')=='repair':z.writestr('source-mission.json',json.dumps(run(result['source_mission']['id']),indent=2,allow_nan=False))
  bundle=result.get('input_bundle_sha256')
  if bundle and (RUNTIME/'gazebo-inputs'/(bundle+'.json')).is_file():z.write(RUNTIME/'gazebo-inputs'/(bundle+'.json'),'gazebo/input-bundle.json')
  z.writestr('README.txt','Clavius simulation evidence. Numerical results are conditional on the recorded inputs and model assumptions. NASA sources and hashes are in assessment.json. Terrain and ephemeris source files must be fetched by their manifest URLs to reproduce. Use scripts/reproduce_simulation.py in the Clavius checkout with this export to rerun and compare metrics. '+('The recorded backend source and dependencies are included.' if snapshot.is_dir() else 'This older run predates source snapshots; recorded implementation bytes are unavailable.')+'\n')
 return Response(raw.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="clavius-{identity}.zip"'})

class CompareRequest(BaseModel):
 run_ids:list[str]=Field(min_length=2,max_length=6)
@app.post('/api/v1/comparisons')
def compare(request:CompareRequest):
 results=[run(i) for i in request.run_ids]
 if len({r['kind'] for r in results})!=1 or any(r['kind'] in {'campaign','repair'} for r in results):raise HTTPException(422,'Select runs of the same kind. Scenario sweeps have their own outcome table.')
 return {'runs':[{'id':r['id'],'name':r['name'],'status':r.get('status'),'request':r.get('request'),'engine':r.get('engine'),'metrics':r.get('metrics'),'first_violation':r.get('first_violation')} for r in results],'policy':'Compare the recorded models and assumptions; these are scenario outcomes, not real-world failure probabilities.'}

from .dynamics import SegmentRequest,simulate_segment
@app.post('/api/v1/robot-segments')
def robot_segment(request:SegmentRequest):
 model=robot(request.robot_id);source=None
 if request.engine=='gazebo':
  capability=GazeboClient().capabilities()
  if not capability.get('available'):raise HTTPException(409,capability['reason'])
 if request.source_run_id:
  source=run(request.source_run_id)
  if source['kind']!='mission' or source['robot_id']!=request.robot_id:raise HTTPException(422,'Choose a mission for this exact robot version.')
  if source['request'].get('site_id','connecting-ridge')!=request.site_id:raise HTTPException(422,'The segment site differs from its source mission. Load that mission site before probing.')
  if source['request'].get('scenario',{}).get('terrain_realization_id','nominal')!=request.terrain_realization_id:raise HTTPException(422,'The segment terrain realization differs from its source mission. Load its recorded surface before probing.')
  if request.mission_offset_s+request.duration_s>source['timeline'][-1]['t_s']:raise HTTPException(422,'The dynamics segment extends past the source mission duration.')
  position,phase=pose_at(request.mission_offset_s,source['phases'])
  request=request.model_copy(update={'east_m':float(position[0]),'north_m':float(position[1]),'heading_deg':float(phase['heading_rad']*180/__import__('math').pi) if 'heading_rad' in phase else 0.})
 def worker(progress,cancel):
  result=GazeboClient().simulate(request,model,progress,cancel) if request.engine=='gazebo' else simulate_segment(request,model,progress,cancel)
  if source:
   from .geometry import epoch,utc_from_et,directions
   from .terrain import site
   start=epoch(source['time_origin_utc'])+request.mission_offset_s
   result['time_origin_utc']=utc_from_et(start)
   result['time_basis']='SPICE ET elapsed SI seconds; detailed segment starts at the source mission offset'
   result['source_mission']={'site_id':request.site_id,'terrain_realization_id':request.terrain_realization_id,'id':source['id'],'input_sha256':source['input_sha256'],'offset_s':request.mission_offset_s,'energy_policy':'Independent physical probe. Does not replace or add to the source mission energy ledger.'}
   result['name']='Rover dynamics · '+source['name']
   for row in result['trace']:
    point=site(request.site_id,request.terrain_realization_id).sample(row['east_m'],row['north_m'])
    row['mission_t_s']=request.mission_offset_s+row['t_s']
    row['utc']=utc_from_et(start+row['t_s'])
    row['sun_enu']=directions(start+row['t_s'],float(point['lat_deg']),float(point['lon_deg']),float(point['elevation_m'])+source['request'].get('observer_height_m',.5))['sun']['enu']
  return result
 return submit('dynamics',request.model_dump(),worker)

@app.post('/api/v1/gazebo-packages')
def gazebo_package(request:SegmentRequest):
 from tempfile import TemporaryDirectory
 from .gazebo_package import make_packet,write_world
 model=robot(request.robot_id);request=request.model_copy(update={'engine':'gazebo'})
 if request.source_run_id:
  source=run(request.source_run_id)
  if source['kind']!='mission' or source['robot_id']!=request.robot_id:raise HTTPException(422,'Choose a mission for this exact robot version.')
  if source['request'].get('site_id','connecting-ridge')!=request.site_id:raise HTTPException(422,'The segment site differs from its source mission. Load that mission site before probing.')
  if source['request'].get('scenario',{}).get('terrain_realization_id','nominal')!=request.terrain_realization_id:raise HTTPException(422,'The segment terrain realization differs from its source mission. Load its recorded surface before probing.')
  if request.mission_offset_s+request.duration_s>source['timeline'][-1]['t_s']:raise HTTPException(422,'The segment extends past the source mission duration.')
  point,phase=pose_at(request.mission_offset_s,source['phases']);request=request.model_copy(update={'east_m':float(point[0]),'north_m':float(point[1]),'heading_deg':phase.get('heading_rad',0)*180/__import__('math').pi})
 try:
  envelope=make_packet(request,model)
  with TemporaryDirectory(prefix='clavius-gazebo-export-') as temporary:
   _,_,_,_,_=write_world(envelope,temporary);raw=io.BytesIO()
   with zipfile.ZipFile(raw,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in Path(temporary).rglob('*'):
     if path.is_file():archive.write(path,str(path.relative_to(temporary)))
    archive.writestr('README.txt','Gazebo input review bundle. This export does not prove Gazebo execution. On the configured Linux worker submit packet.json to POST /jobs. The runtime regenerates world.sdf and local asset paths from the verified packet before executing it. Source posting is 5 m; mesh interpolation is not added measurement resolution.\n')
  return Response(raw.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="clavius-gazebo-inputs.zip"'})
 except ValueError as e:raise HTTPException(422,str(e)) from e

from .scenarios import SweepRequest,sweep
@app.post('/api/v1/scenario-searches')
def scenario_search(request:SweepRequest):
 model=robot(request.mission.robot_id)
 return submit('campaign',request.model_dump(),lambda progress,cancel:sweep(request,model,progress,cancel))

from .repairs import RepairSearchRequest,search as repair_search,candidates as repair_candidates
@app.post('/api/v1/repair-searches')
def find_repairs(request:RepairSearchRequest):
 source=run(request.source_run_id)
 if source.get('kind')!='mission':raise HTTPException(422,'Select a saved mission for repair search.')
 model=robot(source['robot_id'])
 try:repair_candidates(request,MissionRequest(**source['request']))
 except ValueError as e:raise HTTPException(422,str(e)) from e
 return submit('repair',request.model_dump(),lambda progress,cancel:repair_search(request,model,source,progress,cancel))

from .robots import revise_mechanics
@app.put('/api/v1/robots/{identity}/mechanics')
def edit_mechanics(identity:str,body:dict):
 try:return revise_mechanics(robot(identity),body.get('changes'))
 except (ValueError,TypeError) as e:raise HTTPException(422,str(e)) from e
