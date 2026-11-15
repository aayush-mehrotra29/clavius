"""Analytical thermal/energy checks using explicit synthetic unit fixtures."""
import math,json
import numpy as np
import pytest
from pydantic import ValidationError
from clavius.thermal import ThermalConfig,integrate,SIGMA
from clavius.mission import MissionRequest,evaluate
from clavius.paths import ROOT
from clavius.robots import import_robot

POWER={'heater_increment_w':40.,'charge_efficiency':.94,'discharge_efficiency':.95}
def environment(solar=0.,base=2.,incident=0.):
 return lambda t:{'t_s':t,'load_w':base+40,'heater_w':40.,'solar_w':solar,'thermal_solar_irradiance_w_m2':incident}
def config(**changes):
 return ThermalConfig(effective_emission_area_m2=0,ground_conductance_w_k=0,bus_heat_fraction=0,conversion_loss_heat_fraction=0,effective_solar_absorption_area_m2=0,operating_min_c=-250,operating_max_c=150,**changes)
def run(c,duration=1000.,solar=0.,base=2.,energy=425.,heater=False,incident=0.):
 times=[*np.arange(0,duration,60).tolist(),duration]
 return integrate(times,environment(solar,base,incident),c,POWER,500.,energy,heater)

def test_invalid_thermal_properties_are_rejected():
 for values in [{'heat_capacity_j_k':0},{'heater_on_c':5,'heater_off_c':0},{'solar_normal_body_unit':[0,0,2]},{'ground_temperature_c':-300},{'charge_min_c':0,'charge_max_c':1,'charge_hysteresis_k':1},{'effective_emission_area_m2':float('nan')}]:
  with pytest.raises(ValidationError):ThermalConfig(**values)

def test_isolated_node_stays_constant_and_uses_one_energy_ledger():
 rows,events,m=run(config(),duration=3600)
 assert all(row['battery_temperature_c']==20 for row in rows)
 assert rows[-1]['battery_wh']==pytest.approx(425-2/.95)
 assert m['thermal_energy_residual_j']==0
 assert not any(e['severity']=='violation' for e in events)

def test_conductive_cooling_matches_closed_form():
 c=config().model_copy(update={'initial_temperature_c':26.85,'heat_capacity_j_k':1000.,'ground_temperature_c':-173.15,'ground_conductance_w_k':.5})
 rows,_,m=run(c,duration=1000)
 expected=100+(300-100)*math.exp(-.5*1000/1000)
 assert rows[-1]['battery_temperature_c']+273.15==pytest.approx(expected,abs=1e-8)
 assert abs(m['thermal_energy_residual_j'])<1e-7

def test_vacuum_radiative_cooling_matches_closed_form():
 c=config().model_copy(update={'initial_temperature_c':26.85,'heat_capacity_j_k':1000.,'effective_emission_area_m2':.5,'space_view_factor':1.,'space_temperature_k':0.})
 rows,_,m=run(c,duration=100)
 expected=(300**-3+3*.5*SIGMA*100/1000)**(-1/3)
 assert rows[-1]['battery_temperature_c']+273.15==pytest.approx(expected,abs=1e-6)
 assert abs(m['thermal_energy_residual_j'])<1e-7

def test_heater_hysteresis_and_electrical_energy_agree():
 c=config().model_copy(update={'initial_temperature_c':6.85,'heat_capacity_j_k':100.,'ground_temperature_c':-13.15,'ground_conductance_w_k':1.})
 rows,events,m=run(c,duration=1800,heater=True)
 switches=[e for e in events if e['code'] in {'HEATER_ON','HEATER_OFF'}]
 assert len(switches)>20
 for event in switches:
  assert event['state']['battery_temperature_c']==pytest.approx(0 if event['code']=='HEATER_ON' else 5,abs=1e-6)
 first=next(e for e in switches if e['code']=='HEATER_ON')
 assert first['t_s']==pytest.approx(100*math.log((280-260)/(273.15-260)),abs=1e-5)
 heater=sum(a['heater_w']*(b['t_s']-a['t_s'])/3600 for a,b in zip(rows,rows[1:]))
 assert heater==pytest.approx(m['heater_delivered_wh'])
 assert rows[-1]['battery_wh']==pytest.approx(425-(2*1800/3600+heater)/.95,abs=1e-9)
 assert all(a['t_s']<b['t_s'] for a,b in zip(rows,rows[1:]))
 assert abs(m['thermal_energy_residual_j'])<1e-6

def test_cold_charge_inhibition_curtailed_solar_is_not_added_to_soc():
 rows,events,m=run(config(initial_temperature_c=-20),duration=3600,solar=100,base=12)
 assert rows[-1]['battery_wh']==425
 assert all(not row['charge_allowed'] for row in rows)
 assert m['solar_curtailed_wh']==pytest.approx(88)
 assert any(e['code']=='CHARGING_INHIBITED' for e in events)

def test_depleted_battery_does_not_supply_phantom_heater_heat():
 rows,_,m=run(config(initial_temperature_c=-20),duration=3600,energy=0,base=12,heater=True)
 assert all(row['heater_delivered_w']==0 for row in rows)
 assert rows[-1]['battery_temperature_c']==-20
 assert rows[-1]['battery_wh']==0
 assert m['heater_delivered_wh']==0
 assert m['unserved_load_wh']==pytest.approx(52,abs=1e-10)

def test_touching_operating_limit_while_warming_is_not_a_violation():
 c=config().model_copy(update={'initial_temperature_c':0.,'operating_min_c':0.,'heater_on_c':0.,'heater_off_c':5.})
 _,events,_=run(c,duration=60,heater=True)
 assert not any(e['code']=='BATTERY_TOO_COLD' for e in events)

def test_real_site_thermal_run_has_auditable_coupled_energy_and_clock():
 robot=import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'clavius-r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))
 request=MissionRequest(robot_id=robot['id'],duration_hours=.5,waypoints=[{'east_m':0,'north_m':0}],activities=[],thermal=ThermalConfig(initial_temperature_c=1,heat_capacity_j_k=1000))
 result=evaluate(request,robot);energy=425.;rows=result['timeline']
 for a,b in zip(rows,rows[1:]):
  net=a['solar_w']-a['solar_curtailed_w']-a['load_w'];rate=net*.94 if net>=0 else net/.95
  energy=min(500,max(0.,energy+rate*(b['t_s']-a['t_s'])/3600))
  assert energy==pytest.approx(b['battery_wh'],abs=1e-8)
 assert energy==pytest.approx(result['metrics']['final_battery_wh'])
 assert rows[0]['t_s']==0 and rows[-1]['t_s']==1800
 assert all(a['t_s']<b['t_s'] for a,b in zip(rows,rows[1:]))
 assert result['provenance']['models']['thermal']=='lumped-vacuum-battery-v0.1'
 assert result['thermal_model']['source_class']=='declared_engineering_scenario'
 assert any(event['code']=='HEATER_ON' for event in result['events'])

def test_threshold_crossings_and_step_refinement_are_stable():
 c=ThermalConfig(initial_temperature_c=20,heat_capacity_j_k=200,operating_min_c=0,operating_max_c=25,heater_on_c=5,heater_off_c=10)
 def solve(step,heater):return run(c.model_copy(update={'max_step_s':step}),duration=3600,base=12,heater=heater)
 a,ea,ma=solve(1,True);b,eb,mb=solve(.5,True)
 assert [e['code'] for e in ea]==[e['code'] for e in eb]
 for x,y in zip(ea,eb):assert x['t_s']==pytest.approx(y['t_s'],abs=1e-5)
 assert a[-1]['battery_temperature_c']==pytest.approx(b[-1]['battery_temperature_c'],abs=1e-6)
 assert ma['heater_delivered_wh']==pytest.approx(mb['heater_delivered_wh'],abs=1e-7)
 cold,events,_=solve(1,False)
 event=next(e for e in events if e['code']=='BATTERY_TOO_COLD')
 assert event['state']['battery_temperature_c']==pytest.approx(0,abs=1e-6)
 assert cold[-1]['battery_temperature_c']<0

@pytest.mark.parametrize('energy',[10.4,1e-12])
def test_depletion_boundary_is_exact_and_removes_delivered_heat(energy):
 rows,_,m=run(config(initial_temperature_c=-20),duration=1000,energy=energy,base=12,heater=True)
 empty=next(row for row in rows if row['battery_wh']==0)
 assert empty['t_s']==pytest.approx(energy*.95*3600/52,abs=1e-9)
 assert all(row['heater_delivered_w']==0 for row in rows if row['t_s']>=empty['t_s'])
 assert rows[-1]['battery_wh']==0
 assert m['heater_delivered_wh']==pytest.approx(energy*.95*40/52,abs=1e-10)
 assert m['unserved_load_wh']==pytest.approx(52*1000/3600-energy*.95,abs=1e-10)

def test_full_battery_boundary_curtailed_surplus_is_not_conversion_heat():
 rows,_,m=run(config(),duration=1000,energy=490.4,solar=100,base=12)
 full=next(row for row in rows if row['battery_wh']==500)
 fill_s=(500-490.4)*3600/(88*.94)
 assert full['t_s']==pytest.approx(fill_s,abs=1e-9)
 assert rows[-1]['battery_wh']==500
 assert full['conversion_loss_w']==0
 assert m['solar_curtailed_wh']==pytest.approx(88*(1000-fill_s)/3600,abs=1e-10)
