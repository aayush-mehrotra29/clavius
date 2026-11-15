"""Execute and register the native Gazebo/ROS 2 analytical benchmark.

Requires a running Linux worker. No physical result is generated locally.
"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from clavius.gazebo_client import GazeboClient
from clavius.gazebo_package import make_packet
from clavius.dynamics import SegmentRequest
from clavius.robots import import_robot

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url');parser.add_argument('--output',type=Path);args=parser.parse_args()
 client=GazeboClient(url=args.url);capabilities=client.capabilities()
 if not capabilities.get('runtime_available'):
  result={'status':'not_executed','reason':capabilities['reason'],'capabilities':capabilities};print(json.dumps(result,indent=2))
  if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
  raise SystemExit(2)
 robot=import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'clavius-r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()));identities=[]
 for kind,duration,speed in [('flat_drive',5,.05),('free_fall',.5,0)]:
  request=SegmentRequest(robot_id=robot['id'],engine='gazebo',duration_s=duration,speed_m_s=speed)
  envelope=make_packet(request,robot,flat=True,benchmark_kind=kind);job=client.call('/jobs',envelope,timeout=30);identities.append(job['id'])
 for identity in identities:
  deadline=time.monotonic()+600
  while time.monotonic()<deadline:
   state=client.call('/jobs/'+identity)
   if state['state']=='completed':break
   if state['state'] in {'failed','cancelled'}:raise RuntimeError(state['message'])
   time.sleep(.25)
  else:raise TimeoutError('Native benchmark did not finish within ten minutes.')
 result=client.call('/benchmarks/verify',{'job_ids':identities},timeout=30)
 print(json.dumps(result,indent=2))
 if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
