"""Linux Gazebo/ROS 2 worker. Each physics job has its own process and DDS domain."""
import concurrent.futures,hmac,json,os,subprocess,sys,time
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from . import store
from .paths import RUNTIME
from .gazebo_package import PROTOCOL,read_packet,canonical_hash
from .gazebo_runtime import runtime_capabilities

app=FastAPI(title='Clavius Gazebo worker',version='0.1.0')
pool=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='gazebo-broker')
WORK=RUNTIME/'gazebo-jobs';WORK.mkdir(parents=True,exist_ok=True)
for record in store.listing('gazebo_job'):
 if record.get('state') in {'queued','running'}:store.put('gazebo_job',{**record,'state':'failed','message':'The worker restarted before this job completed.'},record['id'])

@app.middleware('http')
async def authorize(request:Request,call_next):
 token=os.environ.get('CLAVIUS_GAZEBO_TOKEN','');authorization=request.headers.get('authorization','')
 if token and not hmac.compare_digest(authorization,'Bearer '+token):
  from fastapi.responses import JSONResponse
  return JSONResponse({'detail':'Worker authorization is required.'},status_code=401)
 if not token and request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:
  from fastapi.responses import JSONResponse
  return JSONResponse({'detail':'A token is required for non-loopback worker access.'},status_code=403)
 return await call_next(request)

def benchmark_status(capabilities):
 path=RUNTIME/'gazebo-benchmark.json'
 if not path.is_file():return {'passed':False,'reason':'The native analytical benchmark has not run.'}
 result=json.loads(path.read_text());matches=result.get('runtime_identity')==capabilities['runtime_identity']
 return {**result,'passed':bool(result.get('passed') and matches),'reason':'Benchmark passed for this runtime.' if matches else 'Runtime identity changed; rerun the analytical benchmark.'}

@app.get('/health')
def health():
 caps=runtime_capabilities();benchmark=benchmark_status(caps)
 return {**caps,'protocol':PROTOCOL,'request_site_identity_version':1,'terrain_realization_version':1,'supported_site_ids':['connecting-ridge','shackleton-rim'],'benchmark':benchmark,'reason':caps.get('reason') if not caps['runtime_available'] else benchmark.get('reason')}

def job(identity):
 value=store.get(identity)
 if not value or value.get('worker_kind')!='gazebo':raise HTTPException(404,'Worker job not found.')
 return value

@app.post('/jobs')
async def submit(request:Request):
 caps=runtime_capabilities()
 if not caps['runtime_available']:raise HTTPException(503,caps['reason'])
 if sum(r.get('state') in {'queued','running'} for r in store.listing('gazebo_job'))>=4:raise HTTPException(429,'Four Gazebo jobs are already queued or running.')
 raw=bytearray()
 async for chunk in request.stream():
  raw.extend(chunk)
  if len(raw)>45*1024*1024:raise HTTPException(413,'Worker input exceeds 45 MB.')
 try:
  envelope=json.loads(raw);packet,_,_=read_packet(envelope)
  if packet.request.engine!='gazebo':raise ValueError('The worker accepts explicitly selected Gazebo requests only.')
 except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e)) from e
 record=store.put('gazebo_job',{'worker_kind':'gazebo','state':'queued','progress':0.,'message':'Queued for Gazebo','input_sha256':envelope['sha256'],'worker_source_sha256':caps['worker_source_sha256'],'runtime_identity':caps['runtime_identity']})
 directory=WORK/record['id'];directory.mkdir();(directory/'packet.json').write_bytes(store.canonical(envelope))
 def execute():
  if (directory/'cancel').exists():store.put('gazebo_job',{**job(record['id']),'state':'cancelled','message':'Cancelled before execution.'},record['id']);return
  store.put('gazebo_job',{**job(record['id']),'state':'running','message':'Starting Gazebo and ROS 2'},record['id'])
  env={**os.environ,'ROS_DOMAIN_ID':str(50+int(record['id'].replace('-','')[:6],16)%150),'GZ_PARTITION':'clavius_'+record['id']}
  try:
   with (directory/'runtime.log').open('wb') as log:
    completed=subprocess.run([sys.executable,'-m','clavius.gazebo_runtime',str(directory)],stdout=log,stderr=subprocess.STDOUT,env=env,timeout=max(120,packet.request.duration_s*10))
   if (directory/'cancel').exists():state='cancelled';message='Gazebo cancellation acknowledged.'
   elif completed.returncode==0 and (directory/'result.json').is_file():
    result=json.loads((directory/'result.json').read_text())
    if result['provenance']['implementation']['source_sha256']!=caps['worker_source_sha256']:raise ValueError('Worker source changed during execution; result rejected.')
    state='completed';message='Gazebo segment completed.'
   else:
    failure=json.loads((directory/'error.json').read_text()) if (directory/'error.json').exists() else {}
    state='failed';message=failure.get('message',f'Gazebo process exited with code {completed.returncode}. Inspect runtime.log on the worker.')
  except Exception as e:state='failed';message=str(e)
  store.put('gazebo_job',{**job(record['id']),'state':state,'progress':1. if state=='completed' else 0.,'message':message},record['id'])
 pool.submit(execute);return record

@app.get('/jobs/{identity}')
def get_job(identity:str):
 value=job(identity);progress=WORK/identity/'progress.json'
 if value['state']=='running' and progress.is_file():
  try:value={**value,**json.loads(progress.read_text())}
  except (ValueError,OSError):pass
 return value

@app.post('/jobs/{identity}/cancel')
def cancel_job(identity:str):
 value=job(identity)
 if value['state'] in {'queued','running'}:(WORK/identity/'cancel').touch()
 return {**value,'cancellation_requested':value['state'] in {'queued','running'}}

@app.get('/jobs/{identity}/result')
def result(identity:str):
 value=job(identity);path=WORK/identity/'result.json'
 if value['state'] not in {'completed','cancelled'} or not path.is_file():raise HTTPException(409,'No completed or explicitly partial result is available.')
 data=json.loads(path.read_text());return {'result':data,'sha256':canonical_hash(data),'partial':value['state']!='completed'}

@app.get('/jobs/{identity}/implementation')
def implementation_files(identity:str):
 value=job(identity);root=RUNTIME/'implementations'/value['worker_source_sha256'];source=root/'clavius'
 if not source.is_dir():raise HTTPException(404,'Recorded worker implementation is unavailable.')
 return {'source_sha256':value['worker_source_sha256'],'files':{p.name:p.read_bytes().decode() for p in source.glob('*.py')},'requirements':(root/'requirements-simulation.txt').read_text()}

@app.post('/benchmarks/verify')
async def verify_benchmarks(request:Request):
 from .gazebo_benchmark import verify_recorded_benchmarks
 body=await request.json()
 try:verified=verify_recorded_benchmarks(body.get('job_ids',[]),job,WORK,runtime_capabilities())
 except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e)) from e
 (RUNTIME/'gazebo-benchmark.json').write_text(json.dumps(verified,indent=2)+'\n');return verified
