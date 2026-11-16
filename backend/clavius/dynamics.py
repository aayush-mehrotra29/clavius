"""Executed native rigid-contact rover dynamics; separate from mission replay.

The backend adapter is explicit: this module uses MuJoCo, not Gazebo. Soil
friction and motor efficiencies are declared inputs, not calibrated regolith.
"""
import math,hashlib,xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from pydantic import BaseModel,Field
from typing import Literal
from .terrain import site,DEG,SiteId,TerrainRealization
from .mission import Cancelled
from .paths import RUNTIME
from .provenance import implementation

class SegmentRequest(BaseModel):
 robot_id:str
 site_id:SiteId='connecting-ridge'
 terrain_realization_id:TerrainRealization='nominal'
 engine:Literal['mujoco','gazebo']='mujoco'
 source_run_id:str|None=None
 mission_offset_s:float=Field(default=0,ge=0,allow_inf_nan=False)
 east_m:float=Field(default=0,ge=-6000,le=6000,allow_inf_nan=False)
 north_m:float=Field(default=0,ge=-6000,le=6000,allow_inf_nan=False)
 heading_deg:float=Field(default=0,ge=-360,le=360,allow_inf_nan=False)
 duration_s:float=Field(default=20,gt=0,le=180,allow_inf_nan=False)
 speed_m_s:float=Field(default=.05,ge=-.15,le=.15,allow_inf_nan=False)
 turn_rate_rad_s:float=Field(default=0,ge=-.2,le=.2,allow_inf_nan=False)
 friction_coefficient:float=Field(default=.7,ge=.1,le=1.5,allow_inf_nan=False)
 motor_efficiency:float=Field(default=.65,gt=0,le=1,allow_inf_nan=False)
 seed:int=Field(default=42,ge=0,le=4294967295)

from .physics_inputs import prepare_scene,UnsupportedDynamics

def fmt(values):return ' '.join(f'{float(x):.10g}' for x in values)
def quat(rpy):
 q=Rotation.from_euler('xyz',rpy).as_quat();return fmt([q[3],*q[:3]])

def build_model(robot,request,terrain=None,flat=False):
 import mujoco
 description=robot['model'];prepared=prepare_scene(robot,request,terrain,flat)
 root=ET.Element('mujoco',model=description['name']);ET.SubElement(root,'compiler',angle='radian',autolimits='true')
 ET.SubElement(root,'option',timestep='.005',gravity='0 0 -1.62',integrator='implicitfast',iterations='50')
 default=ET.SubElement(root,'default');ET.SubElement(default,'geom',friction=f'{request.friction_coefficient} .005 .0001',condim='3',solref='.01 1')
 world=ET.SubElement(root,'worldbody')
 heights=prepared['heights_m'];hmin=prepared['height_min_m'];span=prepared['half_extent_m'];height_range=prepared['height_range_m']
 rotation=prepared['body_to_enu_rotation'];root_z=prepared['root_position_m'][2]
 if flat:ET.SubElement(world,'geom',name='ground',type='plane',size='20 20 .1')
 else:
  asset=ET.SubElement(root,'asset');ET.SubElement(asset,'hfield',name='lunar_terrain',nrow='81',ncol='81',size=f'{span} {span} {height_range} 1')
  ET.SubElement(world,'geom',name='ground',type='hfield',hfield='lunar_terrain',pos=f'0 0 {hmin}')
 root_body=None;collision_conversions=[];links={l['name']:l for l in description['links']};outgoing={name:[j for j in description['joints'] if j['parent']==name] for name in links}
 def add_link(name,parent,joint=None):
  nonlocal root_body
  link=links[name];attributes={'name':name}
  if joint:attributes.update(pos=fmt(joint['origin']['xyz']),quat=quat(joint['origin']['rpy']))
  else:
   q=Rotation.from_matrix(rotation).as_quat();attributes.update(pos=f'0 0 {root_z}',quat=fmt([q[3],*q[:3]]))
  body=ET.SubElement(parent,'body',**attributes)
  if joint is None:root_body=body;ET.SubElement(body,'freejoint',name='root_free')
  elif joint['type']!='fixed':
   attrs={'name':joint['name'],'type':'slide' if joint['type']=='prismatic' else 'hinge','axis':fmt(joint['axis']),'damping':'.01','armature':'.001'}
   if joint['type'] in {'revolute','prismatic'}:
    limit=joint['limits']
    if 'lower' not in limit or 'upper' not in limit:raise UnsupportedDynamics(f'{joint["name"]} needs position limits.')
    attrs['range']=fmt([limit['lower'],limit['upper']])
   ET.SubElement(body,'joint',**attrs)
  inertia=link['inertia_kg_m2'];pose=link['inertial_origin']
  # MJCF fullinertia is expressed in the body frame; rotate authored URDF tensor.
  rot=Rotation.from_euler('xyz',pose['rpy']).as_matrix();tensor=rot@np.array(inertia)@rot.T
  ET.SubElement(body,'inertial',pos=fmt(pose['xyz']),mass=str(link['mass_kg']),fullinertia=fmt([tensor[0,0],tensor[1,1],tensor[2,2],tensor[0,1],tensor[0,2],tensor[1,2]]))
  if not link['collisions']:raise UnsupportedDynamics(f'{name} has no verified collision geometry.')
  for k,g in enumerate(link['collisions']):
   attrs={'name':name+f'_collision_{k}','type':g['type'],'pos':fmt(g['origin']['xyz']),'quat':quat(g['origin']['rpy'])}
   if g['type']=='box':attrs['size']=fmt(np.array(g['size'])/2)
   elif g['type']=='cylinder':attrs['size']=fmt([g['radius'],g['length']/2])
   elif g['type']=='sphere':attrs['size']=str(g['radius'])
   if g['type']=='mesh':
    if not g.get('file'):raise UnsupportedDynamics('Collision mesh is missing from the package.')
    import trimesh
    source=(RUNTIME/'robots'/robot['package_sha256']/g['file']).resolve()
    if not source.is_relative_to((RUNTIME/'robots'/robot['package_sha256']).resolve()):raise UnsupportedDynamics('Invalid collision asset path.')
    try:
     mesh=trimesh.load(source,force='mesh',process=False)
     if len(mesh.vertices)>300000:raise UnsupportedDynamics('Collision mesh exceeds 300,000 vertices; simplify it before importing.')
     mesh.apply_scale(g.get('scale',[1,1,1]));hull=mesh.convex_hull
    except Exception as error:raise UnsupportedDynamics(f'Collision mesh could not be converted: {error}') from error
    if not np.isfinite(hull.vertices).all() or hull.volume<=0:raise UnsupportedDynamics('Collision mesh has no finite nonzero-volume convex hull.')
    converted=source.parent/(source.stem+'-clavius-convex.obj');content=hull.export(file_type='obj').encode();converted.write_bytes(content)
    asset=root.find('asset')
    if asset is None:asset=ET.SubElement(root,'asset')
    mesh_name=f'{name}_hull_{k}';ET.SubElement(asset,'mesh',name=mesh_name,file=str(converted))
    attrs['mesh']=mesh_name
    collision_conversions.append({'link':name,'source':g['file'],'method':'single convex hull, URDF mesh scale applied','sha256':hashlib.sha256(content).hexdigest(),'limits':'Concavities are filled; inspect the collider before relying on clearance.'})
   ET.SubElement(body,'geom',**attrs)
  for child in outgoing[name]:add_link(child['child'],body,child)
 add_link(description['root_link'],world)
 actuators=ET.SubElement(root,'actuator');wheel_settings=prepared['wheels']
 for wheel in wheel_settings:
  effort=wheel['effort_limit_nm'];velocity=wheel['velocity_limit']
  ET.SubElement(actuators,'velocity',name=wheel['joint']+'_motor',joint=wheel['joint'],kv=str(wheel['velocity_gain_nm_s']),forcerange=fmt([-effort,effort]),ctrlrange=fmt([-velocity,velocity]))
 xml=ET.tostring(root,encoding='unicode');model=mujoco.MjModel.from_xml_string(xml)
 if not flat:model.hfield_data[:]=((heights-hmin)/height_range).astype(np.float32).ravel()
 return model,wheel_settings,xml,collision_conversions

def simulate_segment(request,robot,progress=lambda *_:None,cancel=lambda:False,flat=False,controller=None,observe_frame=lambda _:False):
 if request.engine!='mujoco':raise UnsupportedDynamics('Gazebo requests must use the Gazebo worker adapter; no engine substitution is allowed.')
 import mujoco
 terrain=None if flat else site(request.site_id,request.terrain_realization_id);model,wheels,xml,collision_conversions=build_model(robot,request,terrain,flat)
 data=mujoco.MjData(model);mujoco.mj_forward(model,data)
 root_id=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,robot['model']['root_link'])
 profile=robot.get('profile');base=profile['power']['base_bus_power_w'] if profile else 0
 for index,w in enumerate(wheels):
  speed=request.speed_m_s-request.turn_rate_rad_s*w['lateral_m'];omega=speed/w['radius']*w['axis_sign']
  if abs(omega)>w['velocity_limit']:raise UnsupportedDynamics('Requested wheel speed exceeds an imported joint velocity limit.')
  data.ctrl[index]=omega
 steps=math.ceil(request.duration_s/model.opt.timestep);trace=[];max_roll=0;max_pitch=0;contacts_seen=False;bus_energy=0;max_slip=0;distance=0.;previous=data.xpos[root_id][:2].copy();events=[]
 for step in range(steps):
  if step%100==0 and cancel():raise Cancelled()
  if controller and step%10==0:
   # Feedback uses the integrated chassis pose. Wheel commands never set body poses.
   position=data.xpos[root_id]
   rotation=data.xmat[root_id].reshape(3,3)
   speed,turn=controller.command(data.time,position[0]+request.east_m,position[1]+request.north_m,
                                 math.atan2(rotation[1,0],rotation[0,0]))
   for index,w in enumerate(wheels):
    target=(speed-turn*w['lateral_m'])/w['radius']*w['axis_sign']
    data.ctrl[index]=np.clip(target,-w['velocity_limit'],w['velocity_limit'])
  mujoco.mj_step(model,data)
  distance+=float(np.linalg.norm(data.xpos[root_id][:2]-previous));previous=data.xpos[root_id][:2].copy()
  mechanical_w=float(np.sum(np.abs(data.actuator_force*data.actuator_velocity)));bus_w=base+mechanical_w/request.motor_efficiency;bus_energy+=bus_w*model.opt.timestep/3600
  if step%10==0 or step==steps-1:
   rot=data.xmat[root_id].reshape(3,3);angles=Rotation.from_matrix(rot).as_euler('xyz');max_roll=max(max_roll,abs(angles[0]/DEG));max_pitch=max(max_pitch,abs(angles[1]/DEG))
   if not events and max(max_roll,max_pitch)>45:events.append({'t_s':float(data.time),'code':'ATTITUDE_LIMIT','severity':'violation','message':'Body roll or pitch exceeds the declared 45° dynamics screening threshold.'})
   speed=float(np.dot(data.qvel[:3],rot[:,0]));slips=[]
   for w in wheels:
    jid=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,w['joint']);omega=float(data.qvel[model.jnt_dofadr[jid]])*w['axis_sign'];rim=omega*w['radius'];slips.append(float((rim-speed)/max(abs(rim),abs(speed),.01)))
   max_slip=max(max_slip,max(map(abs,slips)));contact_force=0
   for index in range(data.ncon):
    force=np.zeros(6);mujoco.mj_contactForce(model,data,index,force);contact_force+=max(0,float(force[0]))
   contacts_seen|=data.ncon>0;pos=data.xpos[root_id].copy();q=data.xquat[root_id]
   trace.append({'t_s':float(data.time),'east_m':float(pos[0]+request.east_m),'north_m':float(pos[1]+request.north_m),'up_m':float(pos[2]),'quaternion_xyzw':[float(q[1]),float(q[2]),float(q[3]),float(q[0])],'joint_positions':{j['name']:float(data.qpos[model.jnt_qposadr[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,j['name'])]]) for j in robot['model']['joints'] if j['type']!='fixed'},'speed_m_s':speed,'roll_deg':float(angles[0]/DEG),'pitch_deg':float(angles[1]/DEG),'contact_count':int(data.ncon),'total_contact_normal_n':contact_force,'wheel_slip_ratios':slips,'mechanical_w':mechanical_w,'mobility_bus_power_w':bus_w})
   if controller:
    trace[-1]['mobility_bus_energy_wh']=bus_energy
    trace[-1]['activity']=controller.activity
    trace[-1]['waypoint']=controller.index+1
    if observe_frame(trace[-1]) or controller.finished:break
  if step%1000==0:progress(.1+.8*step/steps,f'Integrating rigid-contact dynamics · {data.time:.1f} / {request.duration_s:g} s')
  if not np.isfinite(data.qpos).all() or np.max(np.abs(data.qvel))>100:raise ValueError('Dynamics became numerically unstable; no accepted replay was generated.')
 result={'schema_version':'0.2.0','name':'Detailed rover segment','robot_id':robot['id'],'request':request.model_dump(),'engine':{'name':'MuJoCo','version':mujoco.__version__,'timestep_s':float(model.opt.timestep),'gravity_m_s2':[0,0,-1.62],'terrain_resolution_m':None if flat else 5},'status':'constraint_violated' if events else ('supported_under_assumptions' if contacts_seen else 'insufficient_evidence'),'events':events,'first_violation':events[0] if events else None,'assessment_scope':'rigid-contact wheeled rover dynamics under declared friction; not validated regolith or sub-grid hazard performance','metrics':{'duration_s':float(data.time),'distance_m':distance,'displacement_m':float(np.linalg.norm(data.xpos[root_id][:2])),'maximum_roll_deg':max_roll,'maximum_pitch_deg':max_pitch,'maximum_abs_slip_ratio':max_slip,'mobility_bus_energy_wh':bus_energy,'contacts_observed':contacts_seen},'trace':trace,'issues':[{'code':'ASSUMED_RIGID_SOIL','message':'Friction and motor efficiency are declared. No calibrated lunar sinkage/deformable-regolith model is used.'},{'code':'NATIVE_ADAPTER','message':'This is an executed MuJoCo run. It is not a Gazebo/ROS 2 run.'}],'model_xml':xml,'collision_conversions':collision_conversions,'provenance':{'implementation':implementation(),'robot_package_sha256':robot['package_sha256'],'profile_sha256':robot.get('profile_sha256'),'terrain':None if flat else terrain.manifest,'seed':request.seed}}
 return result
