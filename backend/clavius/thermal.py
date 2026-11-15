"""Declared single-node battery/enclosure thermal screening in vacuum.

Solar forcing comes from the mission's SPICE/terrain environment. Ground and
hardware properties are explicit assumptions, never inferred from imagery.
This integrator owns the coupled battery state when enabled by a mission.
"""
import math
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

SIGMA=5.670374419e-8
MODEL_ID='lumped-vacuum-battery-v0.1'
REFERENCE='https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/'

class GroundReference(BaseModel):
 model_config=ConfigDict(extra='forbid')
 product_id:str=Field(pattern=r'^[a-z0-9_]{1,120}$')
 source_row:int=Field(ge=1,le=10000000)
 derivative_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')

class ThermalConfig(BaseModel):
 model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
 schema_version:Literal['clavius-thermal-1']='clavius-thermal-1'
 initial_temperature_c:float=Field(default=20,gt=-273.15,le=200)
 heat_capacity_j_k:float=Field(default=2700,ge=1,le=1e7)
 effective_emission_area_m2:float=Field(default=.015,ge=0,le=100)
 space_view_factor:float=Field(default=.5,ge=0,le=1)
 space_temperature_k:float=Field(default=3,ge=0,le=500)
 ground_temperature_c:float=Field(default=-173.15,gt=-273.15,le=300)
 ground_reference:GroundReference|None=None
 ground_conductance_w_k:float=Field(default=.01,ge=0,le=1000)
 effective_solar_absorption_area_m2:float=Field(default=.005,ge=0,le=100)
 solar_normal_body_unit:list[float]=Field(default_factory=lambda:[0.,0.,1.],min_length=3,max_length=3)
 bus_heat_fraction:float=Field(default=.1,ge=0,le=1)
 conversion_loss_heat_fraction:float=Field(default=.5,ge=0,le=1)
 heater_on_c:float=Field(default=0,gt=-273.15,le=200)
 heater_off_c:float=Field(default=5,gt=-273.15,le=200)
 operating_min_c:float=Field(default=-10,gt=-273.15,le=200)
 operating_max_c:float=Field(default=50,gt=-273.15,le=200)
 charge_min_c:float=Field(default=0,gt=-273.15,le=200)
 charge_max_c:float=Field(default=45,gt=-273.15,le=200)
 charge_hysteresis_k:float=Field(default=1,ge=.1,le=20)
 max_step_s:float=Field(default=1,ge=.05,le=5)
 @model_validator(mode='after')
 def check_physics(self):
  if self.heater_off_c-self.heater_on_c<.1:raise ValueError('Heater off must exceed heater on by at least 0.1 °C.')
  if self.operating_min_c>=self.operating_max_c:raise ValueError('Operating minimum must be below its maximum.')
  if self.charge_max_c-self.charge_min_c<=2*self.charge_hysteresis_k:raise ValueError('Charging window must exceed twice its hysteresis.')
  if not all(math.isfinite(v) for v in self.solar_normal_body_unit) or abs(sum(v*v for v in self.solar_normal_body_unit)-1)>1e-6:raise ValueError('Thermal solar normal must be a finite unit vector in robot body axes.')
  return self

@dataclass
class State:
 temperature_k:float
 energy_wh:float
 heater_on:bool=False
 charge_mode:str='allowed'
 cold_reported:bool=False
 hot_reported:bool=False

def heat_terms(temperature_k,config,solar_irradiance,internal_w,heater_w,loss_w):
 ground=config.ground_temperature_c+273.15
 radiation=config.effective_emission_area_m2*SIGMA*(config.space_view_factor*(temperature_k**4-config.space_temperature_k**4)+(1-config.space_view_factor)*(temperature_k**4-ground**4))
 return {'absorbed_solar_w':config.effective_solar_absorption_area_m2*solar_irradiance,'internal_heat_w':internal_w*config.bus_heat_fraction,'heater_heat_w':heater_w,'conversion_heat_w':loss_w*config.conversion_loss_heat_fraction,'radiated_heat_w':radiation,'conducted_heat_w':config.ground_conductance_w_k*(temperature_k-ground)}

def net_heat(terms):return terms['absorbed_solar_w']+terms['internal_heat_w']+terms['heater_heat_w']+terms['conversion_heat_w']-terms['radiated_heat_w']-terms['conducted_heat_w']

def rk4(temperature,dt,config,forcing):
 a=heat_terms(temperature,config,*forcing);b=heat_terms(temperature+dt*net_heat(a)/(2*config.heat_capacity_j_k),config,*forcing)
 c=heat_terms(temperature+dt*net_heat(b)/(2*config.heat_capacity_j_k),config,*forcing);d=heat_terms(temperature+dt*net_heat(c)/config.heat_capacity_j_k,config,*forcing)
 average={key:(a[key]+2*b[key]+2*c[key]+d[key])/6 for key in a}
 result=temperature+dt*net_heat(average)/config.heat_capacity_j_k
 if not math.isfinite(result) or result<=0:raise ValueError('Thermal integration left the positive Kelvin domain; revise the declared properties or time step.')
 return result,average

def electrical(state,record,power,capacity,heater_enabled):
 base=record['load_w']-record['heater_w'];heater=power['heater_increment_w'] if state.heater_on and heater_enabled else 0.
 demand=base+heater;solar=record['solar_w'];net=solar-demand
 curtailed=max(0.,net) if state.charge_mode!='allowed' or state.energy_wh>=capacity else 0.
 net-=curtailed
 chemical=net*power['charge_efficiency'] if net>=0 else net/power['discharge_efficiency']
 if state.energy_wh<=0 and chemical<0:chemical=0.
 unserved=max(0.,demand-solar) if state.energy_wh<=0 else 0.
 fraction=(demand-unserved)/demand if demand else 1.
 loss=(net-chemical) if net>=0 else ((-chemical)-max(0.,demand-solar-unserved))
 return {'load_w':demand,'heater_w':heater,'heater_delivered_w':heater*fraction,'delivered_load_w':demand-unserved,'unserved_load_w':unserved,'solar_curtailed_w':curtailed,'battery_rate_w':chemical,'conversion_loss_w':max(0.,loss),'base_delivered_w':base*fraction}

def controls(state,config,heater_enabled,t,events):
 c=state.temperature_k-273.15;old=state.heater_on
 if not heater_enabled:state.heater_on=False
 elif state.heater_on and c>=config.heater_off_c-1e-7:state.heater_on=False
 elif not state.heater_on and c<=config.heater_on_c+1e-7:state.heater_on=True
 if old!=state.heater_on:events.append({'t_s':t,'code':'HEATER_ON' if state.heater_on else 'HEATER_OFF','severity':'info','message':'Thermostat heater switched '+('on.' if state.heater_on else 'off.'),'state':{'battery_temperature_c':c}})
 previous=state.charge_mode
 if state.charge_mode=='cold' and c>=config.charge_min_c+config.charge_hysteresis_k-1e-7:state.charge_mode='allowed'
 elif state.charge_mode=='hot' and c<=config.charge_max_c-config.charge_hysteresis_k+1e-7:state.charge_mode='allowed'
 elif state.charge_mode=='allowed':
  if c<=config.charge_min_c+1e-7:state.charge_mode='cold'
  elif c>=config.charge_max_c-1e-7:state.charge_mode='hot'
 if previous!=state.charge_mode:events.append({'t_s':t,'code':'CHARGING_RESTORED' if state.charge_mode=='allowed' else 'CHARGING_INHIBITED','severity':'info','message':'Charging '+('restored inside the declared temperature window.' if state.charge_mode=='allowed' else 'inhibited by the declared '+state.charge_mode+' temperature threshold.'),'state':{'battery_temperature_c':c}})

def operating_limits(state,config,t,events,heat_w):
 c=state.temperature_k-273.15
 cold=c<config.operating_min_c-1e-7 or (c<=config.operating_min_c+1e-7 and heat_w<0)
 hot=c>config.operating_max_c+1e-7 or (c>=config.operating_max_c-1e-7 and heat_w>0)
 for condition,flag,code,message in [(cold,'cold_reported','BATTERY_TOO_COLD','Battery temperature crosses the declared lower operating limit.'),(hot,'hot_reported','BATTERY_TOO_HOT','Battery temperature crosses the declared upper operating limit.')]:
  if condition and not getattr(state,flag):
   setattr(state,flag,True);events.append({'t_s':t,'code':code,'severity':'violation','message':message,'state':{'battery_temperature_c':c}})

def thresholds(state,config,heater_enabled):
 result=[]
 if heater_enabled:result.append((config.heater_off_c if state.heater_on else config.heater_on_c,1 if state.heater_on else -1))
 if state.charge_mode=='allowed':result.extend([(config.charge_min_c,-1),(config.charge_max_c,1)])
 elif state.charge_mode=='cold':result.append((config.charge_min_c+config.charge_hysteresis_k,1))
 else:result.append((config.charge_max_c-config.charge_hysteresis_k,-1))
 if not state.cold_reported:result.append((config.operating_min_c,-1))
 if not state.hot_reported:result.append((config.operating_max_c,1))
 return [(c+273.15,direction) for c,direction in result]

def advance(state,config,forcing,maximum_dt,limits,cancel,steps):
 """Advance to the next threshold or environment boundary, retaining heat integrals."""
 elapsed=0.;integrals={key:0. for key in heat_terms(state.temperature_k,config,*forcing)};temperature=state.temperature_k
 while elapsed<maximum_dt-1e-9:
  if steps[0]%100==0 and cancel():
   from .mission import Cancelled
   raise Cancelled()
  steps[0]+=1
  if steps[0]>1000000:raise ValueError('Thermal model exceeded one million integration steps; revise stiff properties or hysteresis.')
  terms=heat_terms(temperature,config,*forcing);slope=config.ground_conductance_w_k+4*config.effective_emission_area_m2*SIGMA*max(temperature,config.ground_temperature_c+273.15,config.space_temperature_k)**3
  dt=min(config.max_step_s,maximum_dt-elapsed,.1*config.heat_capacity_j_k/max(slope,1e-20),.05*config.heat_capacity_j_k*temperature/max(abs(net_heat(terms)),1e-20))
  following,average=rk4(temperature,dt,config,forcing)
  crossings=[limit for limit,direction in limits if (temperature-limit)*direction<=1e-8 and (following-limit)*direction>1e-8]
  hit=bool(crossings)
  if hit:
   roots=[]
   for limit in crossings:
    lo=0.;hi=dt
    for _ in range(35):
     mid=(lo+hi)/2;value,_=rk4(temperature,mid,config,forcing)
     if (value<limit)==(temperature<limit):lo=mid
     else:hi=mid
    roots.append(hi)
   dt=min(roots);following,average=rk4(temperature,dt,config,forcing)
  for key,value in average.items():integrals[key]+=value*dt
  elapsed+=dt;temperature=following
  if hit:return elapsed,temperature,integrals
 return elapsed,temperature,integrals

def integrate(times,environment,config,power,capacity,initial_energy,heater_enabled,progress=lambda *_:None,cancel=lambda:False):
 state=State(config.initial_temperature_c+273.15,initial_energy);events=[];rows=[];steps=[0];totals={key:0. for key in heat_terms(state.temperature_k,config,0,0,0,0)}
 initial_temperature=state.temperature_k;minimum=maximum=initial_temperature;heater_wh=curtailed_wh=unserved_wh=0.;t=float(times[0]);index=1
 while True:
  controls(state,config,heater_enabled,t,events);record=dict(environment(t));values=electrical(state,record,power,capacity,heater_enabled)
  forcing=(record['thermal_solar_irradiance_w_m2'],values['base_delivered_w'],values['heater_delivered_w'],values['conversion_loss_w'])
  operating_limits(state,config,t,events,net_heat(heat_terms(state.temperature_k,config,*forcing)))
  row={**record,**values,'t_s':t,'battery_wh':state.energy_wh,'battery_temperature_c':state.temperature_k-273.15,'charge_allowed':state.charge_mode=='allowed','thermal_heater_on':state.heater_on}
  if rows and abs(rows[-1]['t_s']-t)<1e-8:rows[-1]=row
  else:rows.append(row)
  if index>=len(times):break
  maximum_dt=times[index]-t;rate=values['battery_rate_w'];energy_dt=None;energy_limit=None
  if rate>0 and state.energy_wh<capacity:energy_dt=(capacity-state.energy_wh)*3600/rate;energy_limit=capacity
  elif rate<0 and state.energy_wh>0:energy_dt=state.energy_wh*3600/-rate;energy_limit=0.
  if energy_dt is not None:
   maximum_dt=min(maximum_dt,energy_dt)
   # A sub-nanosecond electrical boundary cannot support another thermal step.
   # Snap its negligible remainder instead of stalling or leaving phantom SOC.
   if energy_dt<=1e-9:state.energy_wh=energy_limit;continue
  dt,temperature,heat=advance(state,config,forcing,maximum_dt,thresholds(state,config,heater_enabled),cancel,steps)
  if dt<=1e-9:raise ValueError('Thermal event integration made no forward progress; revise threshold settings.')
  state.energy_wh=min(capacity,max(0.,state.energy_wh+rate*dt/3600))
  if energy_dt is not None and abs(dt-energy_dt)<=1e-9:state.energy_wh=energy_limit
  state.temperature_k=temperature;t+=dt
  for key,value in heat.items():totals[key]+=value
  heater_wh+=values['heater_delivered_w']*dt/3600;curtailed_wh+=values['solar_curtailed_w']*dt/3600;unserved_wh+=values['unserved_load_w']*dt/3600
  minimum=min(minimum,temperature);maximum=max(maximum,temperature)
  if abs(t-times[index])<1e-7:t=float(times[index]);index+=1
  if len(rows)%50==0:progress(.7+.2*t/times[-1],f'Coupling battery temperature and heater demand · {t/3600:.1f} h')
  if len(rows)>50000:raise ValueError('Thermal model generated over 50,000 control transitions; increase hysteresis or revise properties.')
 stored=config.heat_capacity_j_k*(state.temperature_k-initial_temperature);balance=totals['absorbed_solar_w']+totals['internal_heat_w']+totals['heater_heat_w']+totals['conversion_heat_w']-totals['radiated_heat_w']-totals['conducted_heat_w']
 return rows,events,{'minimum_battery_temperature_c':minimum-273.15,'maximum_battery_temperature_c':maximum-273.15,'final_battery_temperature_c':state.temperature_k-273.15,'heater_delivered_wh':heater_wh,'solar_curtailed_wh':curtailed_wh,'unserved_load_wh':unserved_wh,'thermal_energy_residual_j':stored-balance,'thermal_integrator_steps':steps[0],'thermal_heat_integrals_j':totals}
