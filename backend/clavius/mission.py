"""Deterministic route/activity assessment with one energy ledger and explicit scope."""
import hashlib,json,math
from datetime import datetime,timezone
import numpy as np
from pydantic import BaseModel,Field,field_validator,model_validator
from typing import Literal
from .terrain import site,TerrainCoverageError,DEG,SiteId,TerrainRealization
from .geometry import epoch,utc_from_et,directions,solar_disk_fraction,utc_clock_boundaries
from .paths import DATA
from . import store
from .provenance import implementation
from .thermal import ThermalConfig

class Waypoint(BaseModel):
 east_m:float=Field(ge=-6000,le=6000,allow_inf_nan=False)
 north_m:float=Field(ge=-6000,le=6000,allow_inf_nan=False)
class Activity(BaseModel):
 kind:Literal['science','charge','radio','wait']
 waypoint:int=Field(ge=0,le=30)
 duration_s:float=Field(gt=0,le=86400,allow_inf_nan=False)
class Scenario(BaseModel):
 capacity_multiplier:float=Field(default=1,ge=.25,le=1.2,allow_inf_nan=False)
 solar_multiplier:float=Field(default=1,ge=0,le=1.2,allow_inf_nan=False)
 mobility_multiplier:float=Field(default=1,ge=1,le=3,allow_inf_nan=False)
 speed_multiplier:float=Field(default=1,ge=.2,le=1,allow_inf_nan=False)
 terrain_error_sigma:float=Field(default=0,ge=-3,le=3,allow_inf_nan=False)
 terrain_realization_id:TerrainRealization='nominal'
 @model_validator(mode='after')
 def distinct_terrain_models(self):
  if self.terrain_realization_id!='nominal' and self.terrain_error_sigma!=0:raise ValueError('Choose a cloned surface or the legacy observer-height offset, not both.')
  return self
 soil:Literal['assumed_firm','assumed_loose']='assumed_firm'
class MissionRequest(BaseModel):
 robot_id:str
 site_id:SiteId='connecting-ridge'
 name:str=Field(default='Lunar traverse',max_length=100)
 start_utc:str='2028-01-01T00:00:00Z'
 duration_hours:float=Field(default=12,gt=0,le=72,allow_inf_nan=False)
 waypoints:list[Waypoint]=Field(default_factory=lambda:[Waypoint(east_m=0,north_m=0),Waypoint(east_m=60,north_m=0),Waypoint(east_m=100,north_m=35)],min_length=1,max_length=30)
 activities:list[Activity]=Field(default_factory=lambda:[Activity(kind='science',waypoint=1,duration_s=600)],max_length=30)
 heater_enabled:bool=True
 thermal:ThermalConfig|None=None
 observer_height_m:float=Field(default=.5,ge=.05,le=5,allow_inf_nan=False)
 max_earth_outage_s:float=Field(default=21600,ge=0,le=259200,allow_inf_nan=False)
 scenario:Scenario=Field(default_factory=Scenario)
 seed:int=Field(default=42,ge=0,le=2147483647)
 @field_validator('start_utc')
 @classmethod
 def check_time(cls,value):
  try:d=datetime.fromisoformat(value.replace('Z','+00:00'))
  except ValueError as e:raise ValueError('Use an ISO timestamp with a UTC offset.') from e
  if d.tzinfo is None:raise ValueError('Mission epoch must include a timezone or Z.')
  if not 2000<=d.year<=2049:raise ValueError('Supported pinned-kernel mission range is 2000–2049.')
  return d.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
 @model_validator(mode='after')
 def check_activities(self):
  if any(a.waypoint>=len(self.waypoints) for a in self.activities):raise ValueError('An activity refers to a missing waypoint.')
  return self

class Cancelled(Exception):pass

def integrate_energy(energy_wh,generation_w,load_w,dt_s,capacity_wh,charge_efficiency,discharge_efficiency):
 net=generation_w-load_w
 rate=net*charge_efficiency if net>=0 else net/discharge_efficiency
 return min(capacity_wh,max(0.,energy_wh+rate*dt_s/3600)),rate

def build_schedule(request,profile,terrain):
 speed=profile['mobility']['nominal_speed_m_s']*request.scenario.speed_multiplier
 phases=[];t=0;distance=0;heading=0.
 waypoints=[(p.east_m,p.north_m) for p in request.waypoints]
 for i,current in enumerate(waypoints):
  if i:
   previous=waypoints[i-1];length=float(np.linalg.norm(np.array(current)-previous))
   if distance+length>5000:raise ValueError('Route is limited to 5 km per assessment.')
   # Preserve 5 m terrain sampling along the full route, not just at waypoints.
   if length>1e-8:heading=float(np.arctan2(current[1]-previous[1],current[0]-previous[0]))
   subdivisions=int(np.ceil(length/5))
   for k in range(subdivisions):
    a=np.array(previous)+(np.array(current)-previous)*k/subdivisions;b=np.array(previous)+(np.array(current)-previous)*(k+1)/subdivisions
    h0=float(terrain.height(*a));h1=float(terrain.height(*b));horizontal=float(np.linalg.norm(b-a));travel=math.hypot(horizontal,h1-h0);duration=travel/speed
    phases.append({'start_s':t,'end_s':t+duration,'kind':'drive','from':a.tolist(),'to':b.tolist(),'pitch_deg':float(np.arctan2(h1-h0,horizontal)/DEG),'terrain_slope_deg':float(terrain.slope(*(a+b)/2)),'heading_rad':heading,'distance_m':travel})
    t+=duration;distance+=travel
  for activity in [a for a in request.activities if a.waypoint==i]:
   phases.append({'start_s':t,'end_s':t+activity.duration_s,'kind':activity.kind,'from':list(current),'to':list(current),'pitch_deg':0.,'terrain_slope_deg':float(terrain.slope(*current)),'heading_rad':heading,'distance_m':0.});t+=activity.duration_s
 if not phases:phases=[{'start_s':0.,'end_s':0.,'kind':'wait','from':list(waypoints[0]),'to':list(waypoints[0]),'pitch_deg':0.,'terrain_slope_deg':float(terrain.slope(*waypoints[0])),'heading_rad':heading,'distance_m':0.}]
 return phases,distance,t

def pose_at(t,phases):
 for phase in phases:
  if phase['start_s']<=t<phase['end_s']:
   fraction=(t-phase['start_s'])/(phase['end_s']-phase['start_s']);a=np.array(phase['from']);b=np.array(phase['to']);return a+(b-a)*fraction,phase
 last=phases[-1]
 return np.array(last['to']),{**last,'kind':'idle','pitch_deg':0.}

def evaluate(request:MissionRequest,robot,progress=lambda *_:None,cancel=lambda:False):
 if not robot.get('profile'):raise ValueError('Robot needs a validated capability profile before mission analysis.')
 boundary=None
 if request.thermal and request.thermal.ground_reference:
  from .diviner import resolve_boundary
  boundary=resolve_boundary(request.thermal)
  if boundary['source_manifest'].get('selected_site_id','connecting-ridge')!=request.site_id:raise ValueError('The retained Diviner context belongs to a different site. Select this site context or use an explicitly declared ground boundary.')
 terrain=site(request.site_id,request.scenario.terrain_realization_id);profile=robot['profile'];power=profile['power'];scenario=request.scenario
 phases,distance,finish_time=build_schedule(request,profile,terrain)
 duration=request.duration_hours*3600;start=epoch(request.start_utc)
 pcapacity=power['battery_capacity_wh']*scenario.capacity_multiplier;energy=power['initial_soc_fraction']*pcapacity;reserve=power['reserve_wh']
 if reserve>pcapacity:raise ValueError('Scenario battery capacity is below the required reserve.')
 events=[];issues=[]
 if energy<reserve:events.append({'t_s':0,'code':'BATTERY_RESERVE','message':'Initial battery energy is below the mission reserve.','severity':'violation'})
 mobility=profile['mobility'];max_pitch=max(abs(p['pitch_deg']) for p in phases);max_slope=max(p['terrain_slope_deg'] for p in phases)
 if max_slope>mobility['max_supported_slope_deg']:events.append({'t_s':next(p['start_s'] for p in phases if p['terrain_slope_deg']>mobility['max_supported_slope_deg']),'code':'SLOPE_LIMIT','message':f'Selected surface slope along the route exceeds the declared {mobility["max_supported_slope_deg"]:g}° limit, including cross-slope.','severity':'violation'})
 domain=mobility['validity_domain']
 outside=any(p['pitch_deg']<domain['slope_min_deg'] or p['pitch_deg']>domain['slope_max_deg'] for p in phases if p['kind']=='drive')
 if outside:issues.append({'code':'OUTSIDE_RESPONSE_DOMAIN','message':'A route segment lies outside the declared mobility response domain.'})
 if not domain['speed_min_m_s']<=mobility['nominal_speed_m_s']*scenario.speed_multiplier<=domain['speed_max_m_s']:
  outside=True;issues.append({'code':'OUTSIDE_SPEED_DOMAIN','message':'Scenario speed is outside the declared mobility model domain.'})
 if scenario.soil not in domain['soil_categories']:outside=True;issues.append({'code':'UNSUPPORTED_SOIL','message':'Selected soil category is outside the robot response domain.'})
 if finish_time>duration:events.append({'t_s':duration,'code':'TASK_DEADLINE','message':'The route and required activities cannot finish within the mission duration.','severity':'violation'})
 sample_cache={}
 def environment(t):
  if t in sample_cache:return sample_cache[t]
  if cancel():raise Cancelled()
  position,phase=pose_at(t,phases);e,n=map(float,position);point=terrain.sample(e,n)
  if not bool(point['covered']):raise TerrainCoverageError('Route has insufficient local terrain evidence.')
  slope=float(terrain.slope(e,n))
  height=float(point['elevation_m'])+scenario.terrain_error_sigma*float(point['height_rms_m'])
  observer_offset=request.observer_height_m+scenario.terrain_error_sigma*float(point['height_rms_m'])
  geometry=directions(start+t,float(point['lat_deg']),float(point['lon_deg']),height+request.observer_height_m)
  sh,eh=map(float,terrain.horizon_directions(e,n,[geometry['sun']['azimuth_deg'],geometry['earth']['azimuth_deg']],observer_offset))
  visible={'solar_visible_fraction':solar_disk_fraction(geometry['sun']['elevation_deg'],sh,geometry['sun']['angular_radius_deg']),'sun_horizon_deg':sh,'earth_center_visible':geometry['earth']['elevation_deg']>eh}
  dx=(float(terrain.height(e+5,n))-float(terrain.height(e-5,n)))/10;dy=(float(terrain.height(e,n+5))-float(terrain.height(e,n-5)))/10
  heading=phase['heading_rad']
  normal=np.array([-dx,-dy,1.]);normal/=np.linalg.norm(normal)
  forward=np.array([np.cos(heading),np.sin(heading),dx*np.cos(heading)+dy*np.sin(heading)]);forward/=np.linalg.norm(forward)
  left=np.cross(normal,forward);left/=np.linalg.norm(left);body_rotation=np.column_stack([forward,left,normal])
  array=body_rotation@np.array(power['array_normal_body_unit']);sun=np.array(geometry['sun']['enu']);incidence=max(0,float(np.dot(array,sun)))
  irradiance=1361*(149597870.7/geometry['sun']['distance_km'])**2
  generation=power['solar_rated_power_w']*irradiance/power['solar_reference_irradiance_w_m2']*incidence*visible['solar_visible_fraction']*scenario.solar_multiplier
  driving=phase['kind']=='drive';speed=mobility['nominal_speed_m_s']*scenario.speed_multiplier if driving else 0
  gravitational_power=profile['mass_kg']*1.62*speed*max(0,np.sin(phase['pitch_deg']*DEG))/.65 if driving else 0
  base=(power['base_bus_power_w']+(mobility['driving_bus_power_w']-power['base_bus_power_w'])*scenario.mobility_multiplier+gravitational_power) if driving else power['base_bus_power_w']
  heater=power['heater_increment_w'] if request.heater_enabled else 0
  load=base+heater+(power['science_increment_w'] if phase['kind']=='science' else 0)+(power['downlink_increment_w'] if phase['kind']=='radio' else 0)
  record={'t_s':float(t),'east_m':e,'north_m':n,'up_m':float(point['up_m']),'lat_deg':float(point['lat_deg']),'lon_deg':float(point['lon_deg']),'elevation_m':height,'height_rms_m':float(point['height_rms_m']),'terrain_realization_id':scenario.terrain_realization_id,'nominal_lola_return_count':float(point['nominal_lola_return_count']) if np.isfinite(point['nominal_lola_return_count']) else None,'slope_deg':slope,'pitch_deg':phase['pitch_deg'],'heading_rad':heading,'mode':phase['kind'],'solar_w':float(generation),'load_w':float(load),'heater_w':float(heater),'speed_m_s':speed,'solar_visible_fraction':visible['solar_visible_fraction'],'sun_elevation_deg':geometry['sun']['elevation_deg'],'sun_azimuth_deg':geometry['sun']['azimuth_deg'],'sun_enu':geometry['sun']['enu'],'sun_horizon_deg':visible['sun_horizon_deg'],'earth_center_visible':bool(visible['earth_center_visible']),'earth_elevation_deg':geometry['earth']['elevation_deg'],'earth_horizon_deg':eh,'earth_light_time_s':geometry['earth_light_time_s'],'body_quaternion_xyzw':__import__('scipy').spatial.transform.Rotation.from_matrix(body_rotation).as_quat().tolist()}
  if request.thermal:
   thermal_normal=body_rotation@np.array(request.thermal.solar_normal_body_unit)
   record['thermal_solar_irradiance_w_m2']=float(irradiance*max(0.,np.dot(thermal_normal,sun))*visible['solar_visible_fraction'])
  sample_cache[t]=record;return record
 times=set(np.arange(0,duration,60.).tolist()+[duration]+utc_clock_boundaries(start,duration))
 for p in phases:
  times.update(t for t in [p['start_s'],p['end_s']] if 0<=t<=duration)
 coarse=sorted(times);refined=[coarse[0]]
 def refine(a,b,depth=0):
  left=environment(a);right=environment(b)
  transition=abs(left['solar_visible_fraction']-right['solar_visible_fraction'])>.1 or left['earth_center_visible']!=right['earth_center_visible']
  if transition and b-a>1 and depth<7:
   middle=(a+b)/2;refine(a,middle,depth+1);refine(middle,b,depth+1)
  else:refined.append(b)
 for i,(a,b) in enumerate(zip(coarse,coarse[1:])):
  refine(a,b)
  if i%50==0:progress(.1+.6*i/max(1,len(coarse)),f'Sampling lunar conditions · {i+1}/{len(coarse)}')
 thermal_rows=None;thermal_metrics={}
 if request.thermal:
  from .thermal import integrate
  thermal_rows,thermal_events,thermal_metrics=integrate(refined,environment,request.thermal,power,pcapacity,energy,request.heater_enabled,progress,cancel)
  events.extend(thermal_events);refined=[row['t_s'] for row in thermal_rows]
 rows=[];minimum=energy;total_generated=0;total_load=0;outage=0;longest_outage=0;outage_violation=False;reserve_hit=energy<reserve;depleted=energy<=0;prior_visible=None
 for i,t in enumerate(refined):
  row=dict(thermal_rows[i] if thermal_rows is not None else environment(t));row['utc']=utc_from_et(start+t);row['battery_wh']=energy;row['soc_fraction']=energy/pcapacity;rows.append(row)
  if prior_visible is not None and row['earth_center_visible']!=prior_visible:events.append({'t_s':t,'code':'CONTACT_RESTORED' if row['earth_center_visible'] else 'CONTACT_LOST','severity':'info','message':'Geometric Earth-center visibility restored.' if row['earth_center_visible'] else 'Terrain blocks geometric Earth-center visibility.'})
  prior_visible=row['earth_center_visible']
  if i==len(refined)-1:break
  dt=refined[i+1]-t
  if thermal_rows is None:next_energy,rate=integrate_energy(energy,row['solar_w'],row['load_w'],dt,pcapacity,power['charge_efficiency'],power['discharge_efficiency'])
  else:next_energy=thermal_rows[i+1]['battery_wh'];rate=row['battery_rate_w']
  total_generated+=row['solar_w']*dt/3600;total_load+=row['load_w']*dt/3600
  if not reserve_hit and next_energy<reserve:
   crossing=t+(energy-reserve)*3600/(-rate) if rate<0 else t
   events.append({'t_s':crossing,'code':'BATTERY_RESERVE','severity':'violation','message':'Battery falls below the required reserve. Solar generation is insufficient for the active loads.','state':{'solar_w':row['solar_w'],'load_w':row['load_w'],'mode':row['mode'],'solar_visible_fraction':row['solar_visible_fraction']}});reserve_hit=True
  if not depleted and next_energy<=0:
   events.append({'t_s':t+energy*3600/(-rate) if rate<0 else t,'code':'BATTERY_DEPLETED','severity':'violation','message':'Battery is depleted. Later route states are counterfactual scheduled states; actual operations would stop.'});depleted=True
  if row['earth_center_visible']:outage=0
  else:
   previous_outage=outage;outage+=dt;longest_outage=max(longest_outage,outage)
   if not outage_violation and previous_outage<=request.max_earth_outage_s<outage:
    events.append({'t_s':t+request.max_earth_outage_s-previous_outage,'code':'CONTACT_OUTAGE_LIMIT','severity':'violation','message':f'Continuous geometric Earth-center outage exceeds the declared {request.max_earth_outage_s/3600:g} h limit.'})
    outage_violation=True
  energy=next_energy;minimum=min(minimum,energy)
 previous_kind=None
 for phase in phases:
  if phase['kind']!=previous_kind and phase['start_s']<=duration:
   events.append({'t_s':phase['start_s'],'code':'ACTIVITY_'+phase['kind'].upper(),'severity':'info','message':f'{phase["kind"].capitalize()} activity starts.'})
  previous_kind=phase['kind']
 if finish_time<=duration:events.append({'t_s':finish_time,'code':'SCHEDULE_COMPLETE','severity':'info','message':'The planned route and required activities are scheduled complete. Energy support remains a separate assessment.'})
 issues.extend([{'code':'DECLARED_MOBILITY','message':'Travel speed and baseline power are user-declared, not calibrated lunar wheel–soil predictions.'},{'code':'UNRESOLVED_SUBGRID_HAZARDS','message':'5 m terrain cannot establish wheel-scale clearance or rock hazards.'},{'code':'HEATER_ASSUMPTION','message':'Heater power is a declared load. Battery/component temperatures are not predicted.'},{'code':'HORIZON_APPROXIMATION','message':'Horizons trace the exact Sun/Earth-center azimuth at the actual route position to 220 km. Radial sampling and finite-disk approximation still require convergence/observed-shadow validation.'}])
 if scenario.terrain_realization_id!='nominal':issues.append({'code':'PUBLISHED_TERRAIN_REALIZATION','message':'A published NASA statistical cloned surface drives terrain, slope, horizons and power geometry. The fixed nominal ENU origin and nominal regional PGDA90 surface are retained. This bounded subset is not a calibrated mission-risk distribution.'})
 if scenario.terrain_error_sigma:issues.append({'code':'HEIGHT_SCENARIO_LIMIT','message':'Height RMS offsets change observer height only; they are not correlated terrain-error realizations and do not replace horizon resimulation.'})
 violations=sorted([e for e in events if e['severity']=='violation'],key=lambda e:e['t_s']);status='constraint_violated' if violations else ('insufficient_evidence' if outside else 'supported_under_assumptions')
 events.sort(key=lambda e:e['t_s'])
 result={'schema_version':'0.2.0','name':request.name,'request':request.model_dump(),'robot_id':robot['id'],'robot_profile_sha256':robot['profile_sha256'],'time_origin_utc':utc_from_et(start),'time_basis':'SPICE ET elapsed SI seconds from UTC origin','assessment_scope':'declared-model route/activity energy and geometric visibility screening; not certified traversal or mission safety','status':status,'metrics':{'distance_m':distance,'scheduled_completion_s':finish_time,'minimum_battery_wh':minimum,'reserve_wh':reserve,'capacity_wh':pcapacity,'final_battery_wh':energy,'generated_wh':total_generated,'consumed_wh':total_load,'max_route_pitch_deg':max_pitch,'max_terrain_slope_deg':max_slope,'longest_earth_outage_s':longest_outage,'required_tasks_scheduled_complete':finish_time<=duration,'operations_energy_supported':not depleted},'timeline':rows,'events':events,'issues':issues,'phases':phases,'first_violation':violations[0] if violations else None,'provenance':{'implementation':implementation(),'terrain':terrain.manifest,'kernels':json.loads((DATA/'kernels/manifest.json').read_text()),'models':{'environment':'spice-de421-directional-horizon-v0.2','terrain':'pgda78-published-clones-v0.1','energy':'single-ledger-v0.1','mobility':mobility['response_model_id'],'thermal':'declared-heater-load','regolith':'declared-mobility-scenario'},'seed':request.seed,'integration':'left-constant loads; 60 s base grid; activity boundaries; visibility transitions refined to <=1 s'}}
 if request.thermal:
  from .thermal import MODEL_ID,REFERENCE,SIGMA
  result['metrics'].update(thermal_metrics)
  result['issues']=[item for item in result['issues'] if item['code']!='HEATER_ASSUMPTION']
  result['issues'].append({'code':'DECLARED_THERMAL_PROPERTIES','message':'Battery/enclosure temperature uses one uniform node with declared effective areas, heat capacity, heat fractions and a constant ground boundary. Hardware thermal properties are not calibrated. '+('The ground value was copied from a historical Diviner composite, not predicted for this mission date. ' if boundary else 'No Diviner temperature is used in this run. ')+'Post-depletion trajectory states remain counterfactual.'})
  result['thermal_model']={'id':MODEL_ID,'properties':request.thermal.model_dump(),'source_class':'declared_engineering_scenario','reference':REFERENCE,'stefan_boltzmann_w_m2_k4':SIGMA,'limitations':['One uniform battery/enclosure temperature; no internal gradients or separate chassis model.','Constant declared ground temperature; no instantaneous Diviner surface prediction.','Solar absorption area is net effective heat absorption after electrical conversion.','Available solar serves loads first; unserved demand proportionally reduces delivered heater/electronics heat after depletion.','Capacity and voltage are not functions of temperature; charging is inhibited by declared thresholds with hysteresis.']}
  result['provenance']['models']['thermal']=MODEL_ID
  if boundary:
   result['thermal_model']['ground_boundary']=boundary
   result['provenance']['diviner']=boundary['source_manifest']
   result['provenance']['models']['thermal_boundary']='historical-diviner-constant-scenario-v0.1'
  result['provenance']['integration']+='; thermal RK4 with adaptive stability bound and max '+str(request.thermal.max_step_s)+' s step; threshold roots refined by bisection; heater/charging/full/depleted boundaries retained in the same electrical ledger'
  result['assessment_scope']+='; parameterized battery/enclosure thermal screening with thermostat and charging inhibition'
 progress(.95,'Saving reproducible assessment')
 result['input_sha256']=store.artifact({'request':request.model_dump(),'robot':robot['profile_sha256'],'terrain':terrain.manifest,'kernels':result['provenance']['kernels'],'models':result['provenance']['models'],'diviner':result['provenance'].get('diviner'),'implementation':implementation()})
 return result
