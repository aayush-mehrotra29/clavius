"""Shared SI/ENU terrain, robot placement and bounded motor configuration."""
import math
import numpy as np
from .paths import RUNTIME
from .terrain import DEG
from .robots import matrix

class UnsupportedDynamics(ValueError):pass

def prepare_scene(robot,request,terrain=None,flat=False):
 description=robot['model']
 if not description['physical_ready']:raise UnsupportedDynamics('Resolve invalid/missing link inertias before detailed dynamics.')
 links={link['name']:link for link in description['links']}
 wheels=[]
 for joint in description['joints']:
  if joint['type']=='fixed' or not ('wheel' in joint['child'].lower() or 'drive' in joint['name'].lower()):continue
  link=links[joint['child']];cylinders=[g for g in link['collisions'] if g['type']=='cylinder']
  if not cylinders:raise UnsupportedDynamics(f'{joint["child"]} needs a cylindrical wheel collider or explicit wheel mapping.')
  radius=max(g['radius'] for g in cylinders);pose=np.array(link['zero_pose_matrix']);axis=pose[:3,:3]@joint['axis']
  if abs(axis[1])<.8:raise UnsupportedDynamics('Wheel axes must be approximately lateral in the robot body frame.')
  effort=joint['limits'].get('effort');velocity=joint['limits'].get('velocity')
  if effort is None or velocity is None or effort<=0 or velocity<=0:raise UnsupportedDynamics('Actuated wheel joints need positive effort and velocity limits.')
  target=(request.speed_m_s-request.turn_rate_rad_s*float(pose[1,3]))/radius*float(np.sign(axis[1]))
  if abs(target)>velocity:raise UnsupportedDynamics('Requested wheel speed exceeds an imported joint velocity limit.')
  wheels.append({'joint':joint['name'],'radius':radius,'lateral_m':float(pose[1,3]),'axis_sign':float(np.sign(axis[1])),'velocity_limit':velocity,'effort_limit_nm':effort,'target_rad_s':target,'velocity_gain_nm_s':5.})
 if len(wheels)<2:raise UnsupportedDynamics('Map at least two actuated wheel joints to run this wheeled-rover adapter.')
 span=max(20.,abs(request.speed_m_s)*request.duration_s+5)
 if flat:heights=np.zeros((81,81));initial_up=0.;dx=dy=0.
 else:
  axis=np.linspace(-span,span,81);e,n=np.meshgrid(axis+request.east_m,axis+request.north_m);heights=terrain.height(e,n)
  initial_up=float(terrain.height(request.east_m,request.north_m));e0,n0=request.east_m,request.north_m
  dx=(float(terrain.height(e0+5,n0))-float(terrain.height(e0-5,n0)))/10;dy=(float(terrain.height(e0,n0+5))-float(terrain.height(e0,n0-5)))/10
 heading=request.heading_deg*DEG;up=np.array([-dx,-dy,1]);up/=np.linalg.norm(up)
 forward=np.array([np.cos(heading),np.sin(heading),dx*np.cos(heading)+dy*np.sin(heading)]);forward/=np.linalg.norm(forward)
 rotation=np.column_stack([forward,np.cross(up,forward),up]);bottom=math.inf
 for link in description['links']:
  if not link['collisions']:raise UnsupportedDynamics(f'{link["name"]} has no verified collision geometry.')
  for geometry in link['collisions']:
   transform=np.array(link['zero_pose_matrix'])@matrix(geometry['origin']);z=transform[2,:3]
   if geometry['type']=='box':low=transform[2,3]-float(np.dot(np.abs(z),np.array(geometry['size'])/2))
   elif geometry['type']=='cylinder':low=transform[2,3]-geometry['radius']*np.linalg.norm(z[:2])-geometry['length']/2*abs(z[2])
   elif geometry['type']=='sphere':low=transform[2,3]-geometry['radius']
   elif geometry['type']=='mesh':
    import trimesh
    source=(RUNTIME/'robots'/robot['package_sha256']/geometry['file']).resolve()
    if not source.is_relative_to((RUNTIME/'robots'/robot['package_sha256']).resolve()):raise UnsupportedDynamics('Invalid collision asset path.')
    mesh=trimesh.load(source,force='mesh',process=False)
    if len(mesh.vertices)>300000:raise UnsupportedDynamics('Collision mesh exceeds 300,000 vertices; simplify it before importing.')
    vertices=np.asarray(mesh.vertices)*geometry.get('scale',[1,1,1]);low=float(np.min(vertices@z+transform[2,3]))
   else:raise UnsupportedDynamics('Collider support bounds are unavailable.')
   bottom=min(bottom,low)
 if not math.isfinite(bottom):raise UnsupportedDynamics('No finite collision support surface was found.')
 return {'heights_m':heights,'half_extent_m':span,'height_min_m':float(heights.min()),'height_range_m':max(.01,float(heights.max()-heights.min())),'root_position_m':[0.,0.,initial_up+(.025-bottom)/max(.1,float(rotation[2,2]))],'body_to_enu_rotation':rotation,'wheels':wheels,'native_resolution_m':None if flat else 5.,'flat_benchmark':flat,'frame':'local ENU; world X/Y translated by segment east/north; Z is site-local up'}
