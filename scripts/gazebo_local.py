"""Start and inspect Clavius's private Gazebo worker on an Apple Silicon Mac."""
import argparse,json,os,platform,secrets,shutil,subprocess,sys,time
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'data/runtime'
CONFIG=STATE/'docker-client'
ENV_FILE=STATE/'gazebo-local.env'
SOCKET=Path(os.environ.get('COLIMA_HOME',str(Path.home()/'.colima')))/'clavius/docker.sock'

def run(args,**kwargs):return subprocess.run(args,cwd=ROOT,check=True,**kwargs)
def configuration():
 STATE.mkdir(parents=True,exist_ok=True)
 if not ENV_FILE.exists():
  fd=os.open(ENV_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as output:output.write('CLAVIUS_GAZEBO_URL=http://127.0.0.1:8002\nCLAVIUS_GAZEBO_TOKEN='+secrets.token_urlsafe(32)+'\n')
 return dict(line.split('=',1) for line in ENV_FILE.read_text().splitlines() if line and not line.startswith('#'))
def docker(*args,**kwargs):
 return subprocess.run(['docker','--config',str(CONFIG),'--host','unix://'+str(SOCKET),*args],cwd=ROOT,**kwargs)
def health():
 values=configuration()
 request=Request(values['CLAVIUS_GAZEBO_URL']+'/health',headers={'Authorization':'Bearer '+values['CLAVIUS_GAZEBO_TOKEN']})
 return json.load(urlopen(request,timeout=5))

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('action',choices=['start','status','benchmark','stop'])
 parser.add_argument('--build',action='store_true',help='Rebuild the image and replace the local worker container.')
 parser.add_argument('--fresh-sdk',action='store_true',help='Build the native SDK again from the official ROS base image.')
 args=parser.parse_args()
 if args.fresh_sdk:args.build=True
 if platform.system()!='Darwin' or platform.machine()!='arm64':parser.error('This launcher targets Apple Silicon macOS. Use workers/gazebo/README.md for a Linux host.')
 if not all(shutil.which(name) for name in ['colima','docker','brew']):parser.error('Install the local tools first: brew install colima docker docker-buildx')
 prefix=subprocess.check_output(['brew','--prefix'],text=True).strip()
 CONFIG.mkdir(parents=True,exist_ok=True);(CONFIG/'config.json').write_text(json.dumps({'cliPluginsExtraDirs':[prefix+'/lib/docker/cli-plugins']}))
 values=configuration()
 if args.action=='stop':
  docker('stop','--timeout','20','clavius-gazebo',check=True)
  run(['colima','--profile','clavius','stop']);return
 if args.action=='start':
  run(['colima','start','clavius','--cpus','2','--memory','4','--disk','8','--root-disk','4','--arch','aarch64','--vm-type','vz','--runtime','docker','--mount','none','--activate=false','--ssh-config=false','--binfmt=false'])
  image=docker('image','inspect','clavius-gazebo:local',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  if args.build or image.returncode:
   base=[] if args.fresh_sdk or image.returncode else ['--build-arg','ROS_IMAGE=clavius-gazebo:local']
   docker('build',*base,'--tag','clavius-gazebo:local','--file','workers/gazebo/Dockerfile','.',check=True)
  container=docker('inspect','clavius-gazebo',capture_output=True,text=True)
  if args.build and container.returncode==0:
   docker('stop','--timeout','20','clavius-gazebo',check=True);docker('rm','clavius-gazebo',check=True);container=None
  if container is not None and container.returncode==0:
   if not json.loads(container.stdout)[0]['State']['Running']:docker('start','clavius-gazebo',check=True)
  else:
   docker('run','--detach','--name','clavius-gazebo','--init','--memory','2g','--cpus','2','--publish','127.0.0.1:8002:8002','--mount','type=volume,source=clavius-gazebo-state,target=/var/lib/clavius','--env-file',str(ENV_FILE),'clavius-gazebo:local',check=True)
  deadline=time.monotonic()+60
  while True:
   try:report=health();break
   except OSError:
    if time.monotonic()>=deadline:raise RuntimeError('Worker did not become reachable. Inspect docker logs for clavius-gazebo.')
    time.sleep(.5)
  if not report['runtime_available']:raise RuntimeError(report['reason'])
  print('Local worker is running. Use the benchmark command if its runtime has changed.')
 if args.action=='benchmark':
  run([str(ROOT/'.venv/bin/python'),'scripts/benchmark_gazebo_worker.py','--output','docs/validation/gazebo-native-benchmark.json'],env={**os.environ,**values})
 report=health()
 print(json.dumps({key:report.get(key) for key in ['runtime_available','gazebo_version','ros_distro','runtime_identity','worker_source_sha256','benchmark','reason']},indent=2))

if __name__=='__main__':
 try:main()
 except (OSError,RuntimeError,subprocess.CalledProcessError) as error:print(str(error),file=sys.stderr);raise SystemExit(1)
