"""Explicit remote Gazebo adapter. Never falls back to another physics engine."""
import json,math,os,time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .gazebo_package import PROTOCOL,make_packet,canonical_hash,read_packet
from .mission import Cancelled
from .paths import RUNTIME

class GazeboUnavailable(ValueError):pass
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*_):return None

class GazeboClient:
 def __init__(self,url=None,token=None):
  self.url=(url if url is not None else os.environ.get('CLAVIUS_GAZEBO_URL','')).rstrip('/')
  self.token=token if token is not None else os.environ.get('CLAVIUS_GAZEBO_TOKEN','')
  if any(c in self.token for c in ['\r','\n']):raise GazeboUnavailable('The worker token contains invalid header characters.')
  parsed=urlsplit(self.url)
  if self.url and (parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):raise GazeboUnavailable('Configure a plain HTTP(S) worker URL without embedded credentials, query or fragment.')
  self.opener=build_opener(NoRedirect())
 def call(self,path,data=None,timeout=5):
  if not self.url:raise GazeboUnavailable('No Gazebo worker is configured. Set CLAVIUS_GAZEBO_URL to a Linux worker; no other engine will be substituted.')
  headers={'Content-Type':'application/json'}
  if self.token:headers['Authorization']='Bearer '+self.token
  request=Request(self.url+path,data=json.dumps(data,allow_nan=False).encode() if data is not None else None,headers=headers)
  try:
   with self.opener.open(request,timeout=timeout) as response:
    raw=response.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:raise GazeboUnavailable('Worker response exceeds 16 MB.')
    return json.loads(raw)
  except HTTPError as e:
   try:detail=json.loads(e.read(4096)).get('detail',str(e.code))
   except Exception:detail=str(e.code)
   raise GazeboUnavailable(f'Gazebo worker returned HTTP {e.code}: {detail}') from e
 def capabilities(self):
  if not self.url:return {'configured':False,'available':False,'reason':'No Linux Gazebo/ROS 2 worker is configured.'}
  try:
   report=self.call('/health',timeout=2)
   if report.get('protocol')!=PROTOCOL:raise GazeboUnavailable('The worker protocol version is incompatible.')
   if report.get('request_site_identity_version')!=1:raise GazeboUnavailable('Worker predates explicit site/frame identities; rebuild the local worker before running a segment.')
   if report.get('terrain_realization_version')!=1:raise GazeboUnavailable('Worker predates explicit terrain realization identities; rebuild before running a segment.')
   ready=bool(report.get('runtime_available') and report.get('benchmark',{}).get('passed') and report.get('benchmark',{}).get('worker_source_sha256')==report.get('worker_source_sha256'))
   return {**report,'configured':True,'available':ready,'reason':report.get('reason') or ('Ready; analytical benchmark passed.' if ready else 'Runtime or physical benchmark is not verified.')}
  except (GazeboUnavailable,URLError,TimeoutError,ValueError,OSError) as e:return {'configured':True,'available':False,'reason':str(e)}
 def simulate(self,request,robot,progress=lambda *_args,**_kwargs:None,cancel=lambda:False,require_benchmark=True,flat=False,envelope=None,expected_worker_source_sha256=None):
  capabilities=self.capabilities()
  if require_benchmark and not capabilities.get('available'):raise GazeboUnavailable(capabilities['reason'])
  if expected_worker_source_sha256 and capabilities.get('worker_source_sha256')!=expected_worker_source_sha256:raise GazeboUnavailable('Reproduction requires the recorded worker implementation; the configured worker version differs.')
  if cancel():raise Cancelled()
  envelope=envelope or make_packet(request,robot,flat=flat)
  packet,_,_=read_packet(envelope)
  if packet.request.model_dump()!=request.model_dump() or packet.robot_id!=robot['id']:raise GazeboUnavailable('The supplied input package differs from the requested segment or robot.')
  cache=RUNTIME/'gazebo-inputs';cache.mkdir(exist_ok=True);(cache/(envelope['sha256']+'.json')).write_text(json.dumps(envelope,allow_nan=False))
  submitted=self.call('/jobs',envelope,timeout=30);identity=submitted['id']
  import re
  if not re.fullmatch(r'[0-9a-f-]{36}',identity):raise GazeboUnavailable('Worker returned an invalid job identity.')
  progress(.02,'Gazebo worker accepted the physical segment',worker_job_id=identity,worker_url=self.url,worker_input_sha256=envelope['sha256'])
  deadline=time.monotonic()+max(120,request.duration_s*10);last_state=None
  while time.monotonic()<deadline:
   if cancel():
    try:self.call('/jobs/'+identity+'/cancel',{},timeout=5)
    except (OSError,GazeboUnavailable):pass
    raise Cancelled()
   try:state=self.call('/jobs/'+identity,timeout=5)
   except (URLError,TimeoutError,OSError):
    # An observation timeout is not evidence that the Gazebo process stopped.
    time.sleep(.5);continue
   last_state=state
   if state['state']=='completed':
    response=self.call('/jobs/'+identity+'/result',timeout=15);result=response['result']
    if response.get('partial'):raise GazeboUnavailable('A partial worker result cannot be accepted as a completed segment.')
    if canonical_hash(result)!=response.get('sha256'):raise GazeboUnavailable('Worker result checksum mismatch.')
    validate_result(result,envelope)
    sources=self.call('/jobs/'+identity+'/implementation',timeout=10);save_worker_sources(sources)
    if sources['source_sha256']!=result['provenance']['implementation']['source_sha256']:raise GazeboUnavailable('Worker implementation snapshot differs from the reported numerical version.')
    result['worker_job']={'id':identity,'url':self.url,'input_sha256':envelope['sha256'],'result_sha256':response['sha256']}
    return result
   if state['state']=='cancelled':raise Cancelled()
   if state['state']=='failed':raise GazeboUnavailable('Gazebo execution failed: '+state.get('message','Unknown worker failure.'))
   progress(min(.94,.03+.9*state.get('progress',0)),state.get('message','Waiting for Gazebo telemetry'))
   time.sleep(.25)
  try:self.call('/jobs/'+identity+'/cancel',{},timeout=5)
  except (OSError,GazeboUnavailable):pass
  raise GazeboUnavailable('The Gazebo observation deadline expired; cancellation was requested. Last observed state: '+str((last_state or {}).get('state','unreachable')))

def validate_result(result,envelope):
 if result.get('input_bundle_sha256')!=envelope['sha256']:raise GazeboUnavailable('Gazebo result refers to different inputs.')
 engine=result.get('engine',{})
 if engine.get('name')!='Gazebo' or engine.get('backend')!='gz.sim8.TestFixture':raise GazeboUnavailable('Result does not identify the requested Gazebo backend.')
 if result.get('robot_id')!=envelope['payload']['robot_id']:raise GazeboUnavailable('Gazebo result refers to a different robot version.')
 rows=result.get('trace',[]);duration=envelope['payload']['request']['duration_s']
 if not 2<=len(rows)<=5000:raise GazeboUnavailable('Gazebo returned no complete physical telemetry trace.')
 previous=-1
 for row in rows:
  keys=['t_s','east_m','north_m','up_m','speed_m_s','roll_deg','pitch_deg','mechanical_w','mobility_bus_power_w']
  if any(not isinstance(row.get(key),(int,float)) or isinstance(row.get(key),bool) or not math.isfinite(row[key]) for key in keys):raise GazeboUnavailable('Gazebo telemetry contains missing or invalid SI values.')
  if row['t_s']<=previous:raise GazeboUnavailable('Gazebo telemetry time is not strictly increasing.')
  previous=row['t_s'];q=row.get('quaternion_xyzw',[])
  if len(q)!=4 or not all(math.isfinite(v) for v in q) or abs(sum(v*v for v in q)-1)>.001:raise GazeboUnavailable('Gazebo pose has an invalid quaternion.')
 if abs(rows[-1]['t_s']-duration)>.006:raise GazeboUnavailable('Gazebo trace does not cover the requested duration.')
 if result['request']!=envelope['payload']['request']:raise GazeboUnavailable('Worker request identity differs from the submitted request.')
 canonical_hash(result) # Reject nonfinite numbers anywhere in the saved evidence.

def save_worker_sources(sources):
 import hashlib,re
 identity=sources.get('source_sha256','');files=sources.get('files',{})
 if not re.fullmatch(r'[0-9a-f]{64}',identity) or not files:raise GazeboUnavailable('Worker source identity is invalid.')
 h=hashlib.sha256()
 for name,value in sorted(files.items()):
  if not re.fullmatch(r'[A-Za-z0-9_]+\.py',name) or not isinstance(value,str):raise GazeboUnavailable('Worker source archive contains an invalid path.')
  h.update(name.encode());h.update(value.encode())
 if h.hexdigest()!=identity:raise GazeboUnavailable('Worker implementation source checksum mismatch.')
 root=RUNTIME/'implementations'/identity/'clavius';root.mkdir(parents=True,exist_ok=True)
 for name,value in files.items():(root/name).write_text(value)
 (root.parent/'requirements-simulation.txt').write_text(sources.get('requirements',''))
