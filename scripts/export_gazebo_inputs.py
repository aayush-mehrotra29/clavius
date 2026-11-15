"""Prepare a measured-terrain Gazebo review bundle without executing physics."""
import argparse,json,sys,zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from clavius.gazebo_package import make_packet,write_world
from clavius.dynamics import SegmentRequest
from clavius.robots import import_robot

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--east',type=float,default=0);parser.add_argument('--north',type=float,default=0);parser.add_argument('--heading',type=float,default=0);args=parser.parse_args()
 robot=import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'clavius-r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))
 request=SegmentRequest(robot_id=robot['id'],engine='gazebo',east_m=args.east,north_m=args.north,heading_deg=args.heading)
 envelope=make_packet(request,robot)
 with TemporaryDirectory(prefix='clavius-gazebo-review-') as temporary:
  write_world(envelope,temporary)
  with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
   for path in Path(temporary).rglob('*'):
    if path.is_file():archive.write(path,str(path.relative_to(temporary)))
   archive.writestr('README.txt','Input review bundle, not an executed Gazebo result. Submit packet.json to the Linux worker POST /jobs endpoint. The native runtime regenerates world.sdf asset paths before loading.\n')
 print(json.dumps({'bundle_sha256':envelope['sha256'],'file':str(args.output),'bytes':args.output.stat().st_size,'native_execution':False},indent=2))
if __name__=='__main__':main()
