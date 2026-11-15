"""Rerun a trusted Clavius evidence ZIP with its captured backend implementation.

Usage: .venv/bin/python scripts/reproduce_simulation.py export.zip
NASA inputs must already be prepared in this checkout. No network calls are made.
Recorded Python source is executed, so use exports you trust.
"""
import argparse,hashlib,json,math,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('export',type=Path);args=parser.parse_args()
 with tempfile.TemporaryDirectory(prefix='clavius-reproduce-') as temporary:
  work=Path(temporary).resolve()
  with zipfile.ZipFile(args.export) as archive:
   if sum(i.file_size for i in archive.infolist())>150*1024*1024:raise ValueError('Export exceeds the supported expanded size.')
   for item in archive.infolist():
    target=(work/item.filename).resolve()
    if not target.is_relative_to(work):raise ValueError('Export contains an unsafe path.')
    if not item.is_dir():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
  recorded=json.loads((work/'assessment.json').read_text())
  if recorded['kind']=='repair':
   source=json.loads((work/'source-mission.json').read_text())
   source_artifact={k:v for k,v in source.items() if k not in {'id','kind','artifact_sha256','scenario_sample'}}
   if source['id']!=recorded['request']['source_run_id'] or hashlib.sha256(canonical(source_artifact)).hexdigest()!=recorded['source_mission']['artifact_sha256']:raise ValueError('Repair source mission identity differs.')
  robot=json.loads((work/'robot.json').read_text());code=work/'implementation/clavius'
  if not code.is_dir():raise ValueError('This older run has no recorded implementation snapshot.')
  h=hashlib.sha256()
  for source in sorted(code.glob('*.py')):h.update(source.name.encode());h.update(source.read_bytes())
  if h.hexdigest()!=recorded['provenance']['implementation']['source_sha256']:raise ValueError('Recorded implementation checksum mismatch.')
  artifact={k:v for k,v in recorded.items() if k not in {'id','kind','artifact_sha256','scenario_sample'}}
  if hashlib.sha256(canonical(artifact)).hexdigest()!=recorded['artifact_sha256']:raise ValueError('Recorded assessment checksum mismatch.')
  runtime=work/'runtime';package=runtime/'robots'/robot['package_sha256'];package.mkdir(parents=True)
  original=work/'robot-package/original-upload.bin'
  if not original.exists() or hashlib.sha256(original.read_bytes()).hexdigest()!=robot['package_sha256']:raise ValueError('Original robot package is missing or its checksum differs.')
  import shutil
  for asset in (work/'robot-package').rglob('*'):
   if asset.is_file():target=package/asset.relative_to(work/'robot-package');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(asset,target)
  runner="""
import json,sys
from clavius.robots import parse_urdf
from clavius.mission import MissionRequest,evaluate
from clavius.dynamics import SegmentRequest,simulate_segment
from clavius.paths import RUNTIME
record=json.load(open(sys.argv[1]));robot=json.load(open(sys.argv[2]))
raw=(RUNTIME/'robots'/robot['package_sha256']/'original-upload.bin').read_bytes()
name=robot.get('package_filename') or ('robot.zip' if raw[:2]==b'PK' else 'robot.urdf')
parsed,_=parse_urdf(raw,name)
assert parsed==robot['model'],'Serialized mechanical model differs from the original URDF.'
request=record['request']
if record['kind']=='repair':
 from clavius.repairs import RepairSearchRequest,search
 source=json.load(open(__import__('pathlib').Path(sys.argv[1]).parent/'source-mission.json'))
 result=search(RepairSearchRequest(**request),robot,source)
 summary=lambda value:[{'id':p['id'],'cost':p['cost'],'nominal':{k:v for k,v in p['nominal'].items() if k!='run_id'},'audit':None if p.get('audit') is None else {**p['audit'],'cases':[{k:v for k,v in a.items() if k!='run_id'} for a in p['audit']['cases']]}} for p in value['candidates']]
 assert summary(result)==summary(record),'Repair candidate/audit outcomes differ.'
 assert result['audit_cases_sha256']==record['audit_cases_sha256'],'Repair audit inputs differ.'
elif record['kind']=='campaign':
 from clavius.scenarios import SweepRequest,sweep
 result=sweep(SweepRequest(**request),robot)
 summary=lambda value:[{k:v for k,v in outcome.items() if k!='run_id'} for outcome in value['outcomes']]
 assert summary(result)==summary(record),'Sweep scenario inputs or outcomes differ.'
elif record['kind']=='mission':result=evaluate(MissionRequest(**request),robot)
elif record.get('engine',{}).get('name')=='Gazebo':
 from clavius.gazebo_client import GazeboClient
 bundle=json.load(open(__import__('pathlib').Path(sys.argv[1]).parent/'gazebo/input-bundle.json'))
 result=GazeboClient().simulate(SegmentRequest(**request),robot,envelope=bundle,expected_worker_source_sha256=record['provenance']['implementation']['source_sha256'])
else:result=simulate_segment(SegmentRequest(**request),robot)
json.dump(result['metrics'],open(sys.argv[3],'w'),allow_nan=False)
"""
  env={**os.environ,'CLAVIUS_ROOT':str(ROOT),'CLAVIUS_RUNTIME':str(runtime),'PYTHONPATH':str(work/'implementation'),'OPENBLAS_NUM_THREADS':'1'}
  terrain=recorded.get('provenance',{}).get('terrain')
  if terrain and terrain.get('definition'):
   terrain_path=work/'captured-site-manifest.json'
   assets={a['id']:a for a in terrain['assets']}
   assets.update({r['asset']['id']:r['asset'] for r in terrain.get('realization_catalogue',[])})
   terrain_path.write_text(json.dumps({'sites':[terrain['definition']],'terrain':{'assets':list(assets.values())},'site_manifests':{terrain['site_id']:terrain}},allow_nan=False))
   env['CLAVIUS_TERRAIN_MANIFEST_PATH']=str(terrain_path)
  if recorded.get('provenance',{}).get('diviner'):
   context_manifest=work/'context/diviner-manifest.json';context_data=work/('context/diviner-'+recorded['provenance']['diviner'].get('selected_site_id','connecting-ridge')+'.json')
   if not context_data.is_file() or not context_manifest.is_file() or json.loads(context_manifest.read_text())!=recorded['provenance']['diviner']:raise ValueError('Recorded Diviner context files are missing or differ from the run.')
   env.update(CLAVIUS_DIVINER_MANIFEST_PATH=str(context_manifest),CLAVIUS_DIVINER_CONTEXT_PATH=str(context_data))
  subprocess.run([sys.executable,'-c',runner,str(work/'assessment.json'),str(work/'robot.json'),str(work/'metrics.json')],env=env,check=True)
  actual=json.loads((work/'metrics.json').read_text());differences=[]
  for key,expected in recorded['metrics'].items():
   value=actual.get(key)
   if isinstance(expected,bool):match=value==expected
   elif isinstance(expected,(int,float)):match=isinstance(value,(int,float)) and math.isclose(value,expected,rel_tol=1e-6,abs_tol=1e-6)
   else:match=value==expected
   if not match:differences.append({'metric':key,'recorded':expected,'reproduced':value})
  print(json.dumps({'run_id':recorded['id'],'reproduced':not differences,'metric_tolerance':'relative/absolute 1e-6','differences':differences,'metrics':actual},indent=2))
  if differences:raise SystemExit(1)
if __name__=='__main__':main()
