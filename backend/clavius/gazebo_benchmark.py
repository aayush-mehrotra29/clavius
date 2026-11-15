"""Analytical gates over recorded native jobs; contract fixtures never pass these gates."""
import hashlib,json,math
from .paths import ROOT
from .gazebo_package import canonical_hash
from .gazebo_client import validate_result

def verify_recorded_benchmarks(identities,get_job,work,capabilities):
 if len(identities)!=2 or len(set(identities))!=2:raise ValueError('Provide the completed flat-drive and free-fall job identities.')
 if not capabilities['runtime_available']:raise ValueError('The native Gazebo/ROS 2 runtime is unavailable.')
 reference_hash=hashlib.sha256((ROOT/'public/robots/clavius-r1.zip').read_bytes()).hexdigest()
 profile_hash=canonical_hash(json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()));cases={}
 for identity in identities:
  job=get_job(identity)
  if job['state']!='completed':raise ValueError('Every benchmark job must have completed natively.')
  if job['runtime_identity']!=capabilities['runtime_identity']:raise ValueError('Benchmark job belongs to another runtime version.')
  envelope=json.loads((work/identity/'packet.json').read_text());result=json.loads((work/identity/'result.json').read_text());validate_result(result,envelope)
  payload=envelope['payload'];kind=payload['benchmark_kind'];request=payload['request']
  if kind not in {'flat_drive','free_fall'} or kind in cases:raise ValueError('Exactly one flat-drive and one free-fall case are required.')
  if payload['robot_package_sha256']!=reference_hash or canonical_hash(payload['robot_profile'])!=profile_hash:raise ValueError('Benchmark must use the bundled unmodified reference rover and profile.')
  if any(abs(request[key])>1e-12 for key in ['east_m','north_m','heading_deg','turn_rate_rad_s']):raise ValueError('Benchmark must use the fixed origin and straight controller.')
  if result['ros2']['received_clock_messages']<3:raise ValueError('ROS 2 clock messages were not observed through DDS.')
  for row in result['trace']:
   if any(abs(value)>3.000001 for value in row['joint_actuator_torques_nm'].values()):raise ValueError('An actuator exceeded the reference 3 N m limit.')
  last=result['trace'][-1];checks={}
  if kind=='flat_drive':
   if request['duration_s']!=5 or request['speed_m_s']!=.05:raise ValueError('Flat-drive benchmark requires five seconds at 0.05 m/s.')
   checks={'speed_m_s':last['speed_m_s'],'distance_m':result['metrics']['distance_m'],'settled_root_up_m':last['up_m'],'maximum_roll_deg':result['metrics']['maximum_roll_deg'],'maximum_pitch_deg':result['metrics']['maximum_pitch_deg']}
   passed=abs(last['speed_m_s']-.05)<.005 and .18<checks['distance_m']<.30 and abs(last['up_m'])<.015 and checks['maximum_roll_deg']<1 and checks['maximum_pitch_deg']<1
  else:
   if request['duration_s']!=.5 or request['speed_m_s']!=0:raise ValueError('Free-fall benchmark requires 0.5 seconds with zero wheel command.')
   expected_up=.025-.5*1.62*.5**2;expected_velocity=-1.62*.5
   checks={'expected_root_up_m':expected_up,'actual_root_up_m':last['up_m'],'expected_vertical_velocity_m_s':expected_velocity,'actual_vertical_velocity_m_s':last['linear_velocity_enu_m_s'][2]}
   passed=abs(last['up_m']-expected_up)<.006 and abs(checks['actual_vertical_velocity_m_s']-expected_velocity)<.015
  if not passed:raise ValueError(f'{kind} did not satisfy the analytical bounds: {checks}')
  cases[kind]={'job_id':identity,'input_bundle_sha256':envelope['sha256'],'result_sha256':canonical_hash(result),'checks':checks,'ros2_clock_messages':result['ros2']['received_clock_messages']}
 return {'passed':True,'worker_source_sha256':capabilities['worker_source_sha256'],'runtime_identity':capabilities['runtime_identity'],'cases':cases,'scope':'Executed native gravity, placement, bounded drive and ROS 2 telemetry benchmark; no measured lunar soil/contact-reaction calibration is implied.'}
