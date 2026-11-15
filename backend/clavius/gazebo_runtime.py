"""Native Gazebo Harmonic physics with ROS 2 telemetry, isolated per process.

Uses gz.sim8.TestFixture, Joint.set_force and Link state queries. Imported
plugin code is never loaded. Native-runtime validation must run on Linux.
"""
import hashlib,importlib,json,math,os,platform,re,subprocess,sys,time,traceback
from functools import lru_cache
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .gazebo_package import PROTOCOL,write_world,canonical_hash
from .provenance import implementation

@lru_cache(maxsize=1)
def runtime_capabilities():
 implementation_record=implementation()
 identity={'worker_source_sha256':implementation_record['source_sha256'],'libraries':implementation_record['libraries'],'python':platform.python_version(),'platform':platform.platform(),'ros_distro':os.environ.get('ROS_DISTRO',''),'gazebo_version':None,'native_packages':{}}
 available=False;reason=''
 try:
  if platform.system()!='Linux':raise RuntimeError('This Gazebo/ROS 2 worker targets Linux with ROS 2 Jazzy and Gazebo Harmonic.')
  sim=importlib.import_module('gz.sim8');importlib.import_module('rclpy')
  getattr(importlib.import_module('gz.math7').Rand,'seed')
  for name in ['TestFixture','Joint','Link','Model','World','world_entity']:getattr(sim,name)
  for name in ['set_force','enable_velocity_check','enable_position_check']:getattr(sim.Joint,name)
  for name in ['world_pose','world_linear_velocity','enable_velocity_checks']:getattr(sim.Link,name)
  for module in ['rosgraph_msgs.msg','geometry_msgs.msg','sensor_msgs.msg']:importlib.import_module(module)
  version=subprocess.run(['gz','sim','--version'],capture_output=True,text=True,timeout=10,check=True)
  matched=re.search(r'\b8\.\d+\.\d+\b',version.stdout+version.stderr)
  if not matched:raise RuntimeError('Gazebo Harmonic (major version 8) could not be identified.')
  identity['gazebo_version']=matched.group()
  if identity['ros_distro']!='jazzy':raise RuntimeError('The verified worker target is ROS 2 Jazzy. Source its setup.bash before starting the worker.')
  packages=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'],capture_output=True,text=True,timeout=10,check=True)
  prefixes=('gz-','libgz-','libsdformat','libdart','python3-gz','ros-jazzy-rclpy','ros-jazzy-rmw','ros-jazzy-fastrtps','ros-jazzy-fastcdr','ros-jazzy-cyclonedds')
  identity['native_packages']={name:version for name,version in (line.split('\t',1) for line in packages.stdout.splitlines()) if name.startswith(prefixes)}
  if not identity['native_packages']:raise RuntimeError('The worker could not record its native Gazebo/DART/ROS package versions.')
  if not any(name.split(':')[0]=='libgz-sim8-plugins' for name in identity['native_packages']):raise RuntimeError('Install libgz-sim8-plugins so the native physics system can load.')
  available=True
 except Exception as e:reason=str(e)
 fingerprint=canonical_hash(identity)
 return {**identity,'runtime_identity':fingerprint,'protocol':PROTOCOL,'runtime_available':available,'reason':reason,'execution_backend':'gz.sim8.TestFixture','telemetry_topics':['/clock','/clavius/pose','/clavius/joints']}

def atomic_json(path,value):
 temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,allow_nan=False));temporary.replace(path)

def run_native(directory):
 caps=runtime_capabilities()
 if not caps['runtime_available']:raise RuntimeError(caps['reason'])
 from gz.sim8 import TestFixture,World,Model,Joint,Link,world_entity
 from gz.math7 import Rand
 import rclpy
 from rosgraph_msgs.msg import Clock
 from geometry_msgs.msg import PoseStamped
 from sensor_msgs.msg import JointState
 directory=Path(directory);envelope=json.loads((directory/'packet.json').read_text())
 packet,robot,prepared,world_meta,world_path=write_world(envelope,directory/'world')
 request=packet.request;Rand.seed(request.seed)
 if Rand.seed()!=request.seed:raise RuntimeError('Gazebo did not retain the requested random seed.')
 rclpy.init();node=rclpy.create_node('clavius_physics_telemetry')
 clock_publisher=node.create_publisher(Clock,'/clock',20);pose_publisher=node.create_publisher(PoseStamped,'/clavius/pose',20);joints_publisher=node.create_publisher(JointState,'/clavius/joints',20)
 received_clock_messages=0
 def observe_clock(message):
  nonlocal received_clock_messages
  received_clock_messages+=1
 subscription=node.create_subscription(Clock,'/clock',observe_clock,20)
 # Verify DDS discovery before running a fast, fixed-step simulation.
 deadline=time.monotonic()+10
 while clock_publisher.get_subscription_count()<1 and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.05)
 if clock_publisher.get_subscription_count()<1:raise RuntimeError('ROS 2 telemetry discovery did not complete.')
 fixture=TestFixture(str(world_path));state={'ready':False,'joints':{},'root':None,'t_s':0.,'torques':{}};rows=[];energy=0.;distance=0.;previous=np.array(prepared['root_position_m'],dtype=float);maximum_roll=0.;maximum_pitch=0.;maximum_slip=0.;events=[]
 all_joints=[joint for joint in robot['model']['joints'] if joint['type']!='fixed'];wheels={wheel['joint']:wheel for wheel in prepared['wheels']};base=robot['profile']['power']['base_bus_power_w'] if robot.get('profile') else 0.
 def pre_update(info,ecm):
  if not state['ready']:
   model=Model(World(world_entity(ecm)).model_by_name(ecm,'rover'))
   if not model.valid(ecm):raise RuntimeError('Gazebo did not construct the rover model.')
   root=Link(model.link_by_name(ecm,world_meta['root_link']));root.enable_velocity_checks(ecm,True);state['root']=root
   for authored in all_joints:
    joint=Joint(model.joint_by_name(ecm,world_meta['joint_names'][authored['name']]))
    if not joint.valid(ecm):raise RuntimeError('Gazebo did not construct an authored joint.')
    joint.enable_position_check(ecm,True);joint.enable_velocity_check(ecm,True);state['joints'][authored['name']]=joint
   state['ready']=True
  for name,wheel in wheels.items():
   joint=state['joints'][name];velocity=joint.velocity(ecm);omega=velocity[0] if velocity else 0.
   torque=float(np.clip(wheel['velocity_gain_nm_s']*(wheel['target_rad_s']-omega),-wheel['effort_limit_nm'],wheel['effort_limit_nm']))
   joint.set_force(ecm,[torque]);state['torques'][name]=torque
 def post_update(info,ecm):
  nonlocal energy,distance,previous,maximum_roll,maximum_pitch,maximum_slip
  t=info.sim_time.total_seconds();dt=info.dt.total_seconds();state['t_s']=t
  root=state['root'];pose=root.world_pose(ecm);velocity=root.world_linear_velocity(ecm)
  if pose is None or velocity is None:raise RuntimeError('Gazebo did not expose the required physical pose/velocity channels.')
  p=pose.pos();q=pose.rot();position=np.array([p.x(),p.y(),p.z()]);quaternion=[q.x(),q.y(),q.z(),q.w()]
  if not np.isfinite([*position,*quaternion]).all():raise RuntimeError('Gazebo produced a nonfinite pose.')
  rotation=Rotation.from_quat(quaternion);angles=rotation.as_euler('xyz');v=np.array([velocity.x(),velocity.y(),velocity.z()]);speed=float(v@rotation.as_matrix()[:,0])
  if previous is not None:distance+=float(np.linalg.norm(position[:2]-previous[:2]))
  previous=position;positions={};velocities={}
  for name,joint in state['joints'].items():
   angle=joint.position(ecm);rate=joint.velocity(ecm)
   if angle is None or rate is None or len(angle)!=1 or len(rate)!=1:raise RuntimeError('Gazebo did not expose the required physical joint position/velocity channels.')
   positions[name]=float(angle[0]);velocities[name]=float(rate[0])
  if not np.isfinite([*v,*positions.values(),*velocities.values()]).all() or np.max(np.abs(v))>100:raise RuntimeError('Gazebo dynamics became numerically unstable.')
  mechanical=sum(abs(state['torques'][name]*velocities[name]) for name in wheels);bus=base+mechanical/request.motor_efficiency;energy+=bus*dt/3600
  maximum_roll=max(maximum_roll,abs(float(angles[0]*180/math.pi)));maximum_pitch=max(maximum_pitch,abs(float(angles[1]*180/math.pi)))
  if not events and max(maximum_roll,maximum_pitch)>45:events.append({'t_s':t,'code':'ATTITUDE_LIMIT','severity':'violation','message':'Body roll or pitch exceeds the declared 45° dynamics screening threshold.'})
  slips=[]
  for name,wheel in wheels.items():
   rim=velocities[name]*wheel['axis_sign']*wheel['radius'];slips.append((rim-speed)/max(abs(rim),abs(speed),.01))
  maximum_slip=max(maximum_slip,max(map(abs,slips)))
  if not rows or t-rows[-1]['t_s']>=.049999 or t>=request.duration_s-1e-8:
   row={'t_s':t,'east_m':float(position[0]+request.east_m),'north_m':float(position[1]+request.north_m),'up_m':float(position[2]),'quaternion_xyzw':quaternion,'joint_positions':positions,'joint_velocities_rad_s':velocities,'joint_actuator_torques_nm':dict(state['torques']),'linear_velocity_enu_m_s':v.tolist(),'speed_m_s':speed,'roll_deg':float(angles[0]*180/math.pi),'pitch_deg':float(angles[1]*180/math.pi),'wheel_slip_ratios':slips,'mechanical_w':mechanical,'mobility_bus_power_w':bus,'contact_count':None,'total_contact_normal_n':None};rows.append(row)
   stamp=Clock();stamp.clock.sec,stamp.clock.nanosec=divmod(round(t*1e9),1000000000);clock_publisher.publish(stamp)
   pose_message=PoseStamped();pose_message.header.stamp=stamp.clock;pose_message.header.frame_id='moon_local_enu';pose_message.pose.position.x=row['east_m'];pose_message.pose.position.y=row['north_m'];pose_message.pose.position.z=row['up_m']
   pose_message.pose.orientation.x=q.x();pose_message.pose.orientation.y=q.y();pose_message.pose.orientation.z=q.z();pose_message.pose.orientation.w=q.w();pose_publisher.publish(pose_message)
   joint_message=JointState();joint_message.header.stamp=stamp.clock;joint_message.name=list(positions);joint_message.position=list(positions.values());joint_message.velocity=[velocities[name] for name in positions];joint_message.effort=[state['torques'].get(name,0.) for name in positions];joints_publisher.publish(joint_message)
   rclpy.spin_once(node,timeout_sec=0)
 # A Python exception crossing this C++ callback boundary can abort the process.
 # Retain the error and fail after the current bounded native step block instead.
 def guarded(callback):
  def update(info,ecm):
   if state.get('error'):return
   try:callback(info,ecm)
   except Exception as error:state['error']=f'{type(error).__name__}: {error}'
  return update
 fixture.on_pre_update(guarded(pre_update));fixture.on_post_update(guarded(post_update));fixture.finalize();server=fixture.server();steps=math.ceil(request.duration_s/.005);cancelled=False
 try:
  for completed in range(0,steps,100):
   if (directory/'cancel').exists():cancelled=True;break
   if not server.run(True,min(100,steps-completed),False):raise RuntimeError('Gazebo server did not complete a requested physics step block.')
   if state.get('error'):raise RuntimeError('Native Gazebo update failed: '+state['error'])
   atomic_json(directory/'progress.json',{'progress':min(1.,state['t_s']/request.duration_s),'message':f'Gazebo rigid-contact integration · {state["t_s"]:.1f} / {request.duration_s:g} s'})
  deadline=time.monotonic()+2
  while received_clock_messages<3 and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.05)
  if not rows:raise RuntimeError('Gazebo produced no physical state telemetry.')
  if not cancelled and abs(rows[-1]['t_s']-request.duration_s)>.006:raise RuntimeError('Gazebo returned an incomplete simulation clock.')
  if received_clock_messages<1:raise RuntimeError('The ROS 2 clock stream was not received through DDS.')
  result={'schema_version':'0.2.0','name':'Gazebo rover segment','robot_id':robot['id'],'request':request.model_dump(),'input_bundle_sha256':envelope['sha256'],'engine':{'name':'Gazebo','version':caps['gazebo_version'],'backend':'gz.sim8.TestFixture','physics':'DART','ros_distro':caps['ros_distro'],'timestep_s':.005,'gravity_m_s2':[0,0,-1.62],'terrain_resolution_m':packet.terrain.native_resolution_m,'motor_control':'bounded proportional velocity servo; authored URDF effort and velocity limits'},'status':'cancelled_partial' if cancelled else ('constraint_violated' if events else 'supported_under_assumptions'),'assessment_scope':'native Gazebo rigid-contact wheel actuation, pose and joint telemetry under declared friction; contact reactions and calibrated regolith are not instrumented','events':events,'first_violation':events[0] if events else None,'metrics':{'duration_s':state['t_s'],'distance_m':distance,'displacement_m':float(np.linalg.norm(previous[:2])),'maximum_roll_deg':maximum_roll,'maximum_pitch_deg':maximum_pitch,'maximum_abs_slip_ratio':maximum_slip,'mobility_bus_energy_wh':energy,'contacts_observed':None},'trace':rows,'world_manifest':world_meta,'world_sdf':world_path.read_text(),'issues':[{'code':'ASSUMED_RIGID_SOIL','message':'Declared rigid friction and motor efficiency; no calibrated lunar sinkage or dust model.'},{'code':'CONTACT_REACTION_UNAVAILABLE','message':'The Python fixture does not currently expose a verified contact-force channel. Contact counts and forces are null, never fabricated.'},{'code':'ENGINE_DIFFERENCE','message':'DART contact and actuation differ from MuJoCo; quantitative agreement requires executed cross-engine validation.'}],'ros2':{'topics':caps['telemetry_topics'],'received_clock_messages':received_clock_messages,'domain_id':int(os.environ.get('ROS_DOMAIN_ID','0')),'time_basis':'Gazebo simulation time; source mission UTC is attached by Clavius'},'provenance':{'implementation':implementation(),'runtime_identity':caps['runtime_identity'],'robot_package_sha256':robot['package_sha256'],'profile_sha256':robot.get('profile_sha256'),'terrain':packet.terrain.source_manifest,'conditioned_terrain_sha256':canonical_hash(packet.terrain.model_dump()),'seed':request.seed,'controller':'fixed requested wheel velocity with 5 N m s proportional gain, bounded by imported torque limits'}}
  atomic_json(directory/'result.json',result)
 finally:node.destroy_node();rclpy.shutdown()

def main():
 directory=Path(sys.argv[1]).resolve()
 try:run_native(directory)
 except Exception as e:
  atomic_json(directory/'error.json',{'type':type(e).__name__,'message':str(e)});traceback.print_exc();raise SystemExit(1)
if __name__=='__main__':main()
