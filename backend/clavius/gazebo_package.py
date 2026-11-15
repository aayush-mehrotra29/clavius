"""Content-pinned Gazebo worker inputs and a data-only SDF world exporter."""
import base64,hashlib,json,math,shutil
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET
import numpy as np
from pydantic import BaseModel,ConfigDict,Field,model_validator
from scipy.ndimage import map_coordinates
from scipy.spatial.transform import Rotation
from . import store
from .paths import RUNTIME
from .dynamics import SegmentRequest
from .physics_inputs import prepare_scene,UnsupportedDynamics
from .robots import import_robot,matrix

PROTOCOL='clavius-gazebo-1'
class TerrainGrid(BaseModel):
 model_config=ConfigDict(extra='forbid')
 width:Literal[81]=81
 height:Literal[81]=81
 half_extent_m:float=Field(ge=20,le=40,allow_inf_nan=False)
 heights_m:list[float]=Field(min_length=6561,max_length=6561)
 native_resolution_m:float|None=5
 source_manifest:dict|None=None
 flat_benchmark:bool=False
 @model_validator(mode='after')
 def check_values(self):
  if not np.isfinite(self.heights_m).all():raise ValueError('Terrain grid must contain finite heights from its recorded scientific surface.')
  if self.flat_benchmark:
   if any(abs(h)>1e-12 for h in self.heights_m) or self.source_manifest is not None:raise ValueError('The flat analytical benchmark cannot be labeled as measured NASA terrain.')
  elif self.native_resolution_m!=5 or not self.source_manifest:raise ValueError('Scientific terrain requires the source manifest and native 5 m posting.')
  return self

class GazeboPacket(BaseModel):
 model_config=ConfigDict(extra='forbid')
 protocol:Literal['clavius-gazebo-1']=PROTOCOL
 request:SegmentRequest
 robot_id:str=Field(pattern=r'^[0-9a-f]{24}$')
 robot_package_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
 robot_model_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
 robot_filename:str=Field(max_length=256)
 robot_upload_base64:str=Field(max_length=42*1024*1024)
 robot_profile:dict|None=None
 terrain:TerrainGrid
 benchmark_kind:Literal['none','flat_drive','free_fall']='none'
 @model_validator(mode='after')
 def check_site_identity(self):
  if not self.terrain.flat_benchmark and self.terrain.source_manifest.get('site_id')!=self.request.site_id:raise ValueError('The worker terrain manifest and requested site differ.')
  if self.terrain.flat_benchmark and self.request.terrain_realization_id!='nominal':raise ValueError('An analytical flat benchmark cannot claim a lunar terrain realization.')
  if not self.terrain.flat_benchmark and self.terrain.source_manifest.get('realization',{}).get('id','nominal')!=self.request.terrain_realization_id:raise ValueError('The worker terrain realization differs from the requested surface.')
  return self

class GridTerrain:
 def __init__(self,packet):
  self.grid=packet.terrain;self.request=packet.request;self.values=np.array(self.grid.heights_m).reshape(81,81)
 def height(self,east,north):
  x,y=np.broadcast_arrays(np.asarray(east),np.asarray(north));span=self.grid.half_extent_m
  col=(x-self.request.east_m+span)*80/(2*span);row=(y-self.request.north_m+span)*80/(2*span)
  if np.any((col<-.000001)|(col>80.000001)|(row<-.000001)|(row>80.000001)):raise ValueError('A query leaves the worker terrain package.')
  result=map_coordinates(self.values,np.stack([row.ravel(),col.ravel()]),order=1,mode='nearest',prefilter=False)
  return result.reshape(x.shape)

def canonical_hash(value):return hashlib.sha256(store.canonical(value)).hexdigest()

def make_packet(request,robot,terrain=None,flat=False,benchmark_kind=None):
 if not flat and terrain is None:
  from .terrain import site
  terrain=site(request.site_id,request.terrain_realization_id)
 prepared=prepare_scene(robot,request,terrain,flat)
 original=RUNTIME/'robots'/robot['package_sha256']/'original-upload.bin'
 if not original.is_file():raise UnsupportedDynamics('This older robot has no retained original upload. Reimport its URDF package before sending it to Gazebo.')
 raw=original.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=robot['package_sha256']:raise ValueError('Original robot package checksum mismatch.')
 packet=GazeboPacket(request=request,robot_id=robot['id'],robot_package_sha256=robot['package_sha256'],robot_model_sha256=canonical_hash(robot['model']),robot_filename=robot.get('package_filename') or ('robot.zip' if raw[:2]==b'PK' else robot['model']['urdf_file']),robot_upload_base64=base64.b64encode(raw).decode(),robot_profile=robot.get('profile'),terrain=TerrainGrid(half_extent_m=prepared['half_extent_m'],heights_m=prepared['heights_m'].ravel().tolist(),native_resolution_m=prepared['native_resolution_m'],source_manifest=None if flat else terrain.manifest,flat_benchmark=flat))
 packet.benchmark_kind=benchmark_kind or ('flat_drive' if flat else 'none')
 payload=packet.model_dump();return {'sha256':canonical_hash(payload),'payload':payload}

def read_packet(envelope):
 if canonical_hash(envelope['payload'])!=envelope.get('sha256'):raise ValueError('Worker input bundle checksum mismatch.')
 packet=GazeboPacket.model_validate(envelope['payload'])
 if packet.terrain.flat_benchmark!=(packet.benchmark_kind!='none'):raise ValueError('Analytical benchmark and terrain labels differ.')
 if packet.request.robot_id!=packet.robot_id:raise ValueError('Request and robot version differ.')
 try:raw=base64.b64decode(packet.robot_upload_base64,validate=True)
 except ValueError as e:raise ValueError('Invalid robot package encoding.') from e
 if hashlib.sha256(raw).hexdigest()!=packet.robot_package_sha256:raise ValueError('Worker robot package checksum mismatch.')
 if Path(packet.robot_filename).name!=packet.robot_filename or not packet.robot_filename.lower().endswith(('.zip','.urdf')):raise ValueError('Worker robot filename must be a local URDF or ZIP basename.')
 robot=import_robot(raw,packet.robot_filename,packet.robot_profile)
 if robot['id']!=packet.robot_id or canonical_hash(robot['model'])!=packet.robot_model_sha256:raise ValueError('Worker reconstruction differs from the selected robot version.')
 prepared=prepare_scene(robot,packet.request,GridTerrain(packet),packet.terrain.flat_benchmark)
 return packet,robot,prepared

def element(parent,tag,text=None,**attributes):
 child=ET.SubElement(parent,tag,attributes)
 if text is not None:child.text=str(text)
 return child

def vec(values):return ' '.join(f'{float(v):.12g}' for v in values)
def pose_values(transform):return [*transform[:3,3],*Rotation.from_matrix(transform[:3,:3]).as_euler('xyz')]

def terrain_collada(grid,path):
 """Triangulated sampled surface, with +Z normals and explicit metre units."""
 ET.register_namespace('','http://www.collada.org/2005/11/COLLADASchema')
 root=ET.Element('COLLADA',xmlns='http://www.collada.org/2005/11/COLLADASchema',version='1.4.1');asset=element(root,'asset');element(asset,'unit',name='meter',meter='1');element(asset,'up_axis','Z_UP')
 library=element(root,'library_geometries');geometry=element(library,'geometry',id='terrain');mesh=element(geometry,'mesh');source=element(mesh,'source',id='positions')
 axis=np.linspace(-grid.half_extent_m,grid.half_extent_m,81);east,north=np.meshgrid(axis,axis);positions=np.column_stack([east.ravel(),north.ravel(),grid.heights_m])
 array=element(source,'float_array',vec(positions.ravel()),id='positions-array',count=str(positions.size));technique=element(source,'technique_common');accessor=element(technique,'accessor',source='#positions-array',count='6561',stride='3')
 for name in ['X','Y','Z']:element(accessor,'param',name=name,type='float')
 # DART's mesh consumer requires one supplied normal per vertex.
 # These normals describe the interpolated grid; they add no measured detail.
 dy,dx=np.gradient(np.array(grid.heights_m).reshape(81,81),2*grid.half_extent_m/80)
 normals=np.column_stack([-dx.ravel(),-dy.ravel(),np.ones(6561)]);normals/=np.linalg.norm(normals,axis=1)[:,None]
 normal_source=element(mesh,'source',id='normals');element(normal_source,'float_array',vec(normals.ravel()),id='normals-array',count=str(normals.size))
 normal_accessor=element(element(normal_source,'technique_common'),'accessor',source='#normals-array',count='6561',stride='3')
 for name in ['X','Y','Z']:element(normal_accessor,'param',name=name,type='float')
 vertices=element(mesh,'vertices',id='vertices');element(vertices,'input',semantic='POSITION',source='#positions');indices=[]
 for row in range(80):
  for col in range(80):
   a=row*81+col;b=a+1;c=a+81;d=c+1;indices.extend([a,b,c,b,d,c])
 triangles=element(mesh,'triangles',count='12800');element(triangles,'input',semantic='VERTEX',source='#vertices',offset='0');element(triangles,'input',semantic='NORMAL',source='#normals',offset='1');element(triangles,'p',' '.join(str(i) for index in indices for i in (index,index)))
 scenes=element(root,'library_visual_scenes');scene=element(scenes,'visual_scene',id='scene');node=element(scene,'node',id='terrain-node');element(node,'instance_geometry',url='#terrain');element(element(root,'scene'),'instance_visual_scene',url='#scene')
 ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def write_world(envelope,directory):
 """Generate only our own physics elements; imported URDF plugin tags never execute."""
 directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
 packet,robot,prepared=read_packet(envelope);description=robot['model'];source=RUNTIME/'robots'/robot['package_sha256']
 for asset in robot['assets']:
  path=directory/'robot'/asset['path'];path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/asset['path'],path)
 link_names={link['name']:f'link_{i}' for i,link in enumerate(description['links'])};joint_names={joint['name']:f'joint_{i}' for i,joint in enumerate(description['joints'])}
 root=ET.Element('sdf',version='1.9');world=element(root,'world',name='clavius');element(world,'gravity','0 0 -1.62')
 physics=element(world,'physics',name='lunar',type='ignored');element(physics,'max_step_size','.005');element(physics,'real_time_factor','0')
 physics_system=element(world,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
 element(element(physics_system,'engine'),'filename','libgz-physics7-dartsim-plugin.so.7')
 if packet.benchmark_kind!='free_fall':
  ground=element(world,'model',name='terrain');element(ground,'static','true');ground_link=element(ground,'link',name='ground');collision=element(ground_link,'collision',name='ground_collision');geometry=element(collision,'geometry')
  if packet.terrain.flat_benchmark:
   plane=element(geometry,'plane');element(plane,'normal','0 0 1');element(plane,'size','200 200')
  else:
   terrain_collada(packet.terrain,directory/'terrain.dae');mesh=element(geometry,'mesh');element(mesh,'uri',(directory/'terrain.dae').as_uri())
 model=element(world,'model',name='rover',canonical_link=link_names[description['root_link']]);element(model,'static','false')
 element(model,'pose',vec([*prepared['root_position_m'],*Rotation.from_matrix(prepared['body_to_enu_rotation']).as_euler('xyz')]))
 for link in description['links']:
  body=element(model,'link',name=link_names[link['name']]);element(body,'pose',vec(pose_values(np.array(link['zero_pose_matrix']))),relative_to='__model__')
  inertial=element(body,'inertial');element(inertial,'pose',vec([*link['inertial_origin']['xyz'],*link['inertial_origin']['rpy']]));element(inertial,'mass',link['mass_kg']);tensor=element(inertial,'inertia');values=link['inertia_kg_m2']
  for key,i,j in [('ixx',0,0),('iyy',1,1),('izz',2,2),('ixy',0,1),('ixz',0,2),('iyz',1,2)]:element(tensor,key,values[i][j])
  for index,g in enumerate(link['collisions']):
   shape=element(body,'collision',name=f'collision_{index}');element(shape,'pose',vec([*g['origin']['xyz'],*g['origin']['rpy']]));geometry=element(shape,'geometry');kind=element(geometry,g['type'])
   if g['type']=='box':element(kind,'size',vec(g['size']))
   elif g['type']=='sphere':element(kind,'radius',g['radius'])
   elif g['type']=='cylinder':element(kind,'radius',g['radius']);element(kind,'length',g['length'])
   elif g['type']=='mesh':element(kind,'uri',(directory/'robot'/g['file']).as_uri());element(kind,'scale',vec(g.get('scale',[1,1,1])))
   surface=element(shape,'surface');friction=element(surface,'friction');ode=element(friction,'ode');element(ode,'mu',packet.request.friction_coefficient);element(ode,'mu2',packet.request.friction_coefficient)
 for joint in description['joints']:
  node=element(model,'joint',name=joint_names[joint['name']],type='revolute' if joint['type']=='continuous' else joint['type']);element(node,'parent',link_names[joint['parent']]);element(node,'child',link_names[joint['child']]);element(node,'pose','0 0 0 0 0 0',relative_to=link_names[joint['child']])
  if joint['type']!='fixed':
   axis=element(node,'axis');element(axis,'xyz',vec(joint['axis']),expressed_in=link_names[joint['child']]);limits=element(axis,'limit')
   if joint['type'] in {'revolute','prismatic'} and not {'lower','upper'}<=joint['limits'].keys():raise UnsupportedDynamics('Non-continuous joints need authored position limits.')
   for key,value in [('lower',joint['limits'].get('lower',-1e16)),('upper',joint['limits'].get('upper',1e16)),('effort',joint['limits'].get('effort',-1)),('velocity',joint['limits'].get('velocity',-1))]:element(limits,key,value)
   dynamics=element(axis,'dynamics');element(dynamics,'damping','.01')
 path=directory/'world.sdf';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
 metadata={'protocol':PROTOCOL,'bundle_sha256':envelope['sha256'],'world_file':'world.sdf','link_names':link_names,'joint_names':joint_names,'root_link':link_names[description['root_link']],'wheels':prepared['wheels'],'terrain_native_resolution_m':packet.terrain.native_resolution_m,'terrain_mesh_spacing_m':packet.terrain.half_extent_m/40,'limits':['Triangulated interpolation does not create additional measured terrain detail.','DART contact/friction differs from MuJoCo; cross-engine agreement must be measured.','The MuJoCo joint armature is not an authored URDF property and is not inserted into this SDF.']}
 (directory/'packet.json').write_bytes(store.canonical(envelope));(directory/'world-manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
 return packet,robot,prepared,metadata,path
