"""Generate a transparent, hypothetical four-wheel baseline; not NASA hardware."""
import io,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'public/robots';out.mkdir(exist_ok=True)
body='''<robot name="Clavius R1 (hypothetical)">
<link name="base_link">
<inertial><origin xyz="0 0 0.4"/><mass value="20"/><inertia ixx="1.45" ixy="0" ixz="0" iyy="2.1" iyz="0" izz="2.8"/></inertial>
<visual><origin xyz="0 0 0.4"/><geometry><box size="0.85 0.56 0.22"/></geometry></visual>
<collision><origin xyz="0 0 0.4"/><geometry><box size="0.85 0.56 0.22"/></geometry></collision>
</link>'''
for name,x,y in [('front_left',.32,.37),('front_right',.32,-.37),('rear_left',-.32,.37),('rear_right',-.32,-.37)]:
 body+=f'''<link name="{name}_wheel">
<inertial><mass value="1"/><inertia ixx="0.00693" ixy="0" ixz="0" iyy="0.0128" iyz="0" izz="0.00693"/></inertial>
<visual><origin rpy="1.57079632679 0 0"/><geometry><cylinder radius="0.16" length="0.08"/></geometry></visual>
<collision><origin rpy="1.57079632679 0 0"/><geometry><cylinder radius="0.16" length="0.08"/></geometry></collision>
</link>
<joint name="{name}_drive" type="continuous"><origin xyz="{x} {y} 0.16"/><parent link="base_link"/><child link="{name}_wheel"/><axis xyz="0 1 0"/><limit effort="3" velocity="3"/></joint>'''
body+='</robot>'
profile=json.loads((root/'examples/integration/robot-capability.json').read_text())
profile.update(robot_id='clavius-r1',name='Clavius R1 (hypothetical)',mass_kg=24,dimensions_m=[.96,.82,.51],center_of_mass_body_m=[0,0,.36],wheel_count=4,ground_clearance_m=.29)
profile['power'].update(battery_capacity_wh=500,initial_soc_fraction=.85,reserve_wh=75,charge_efficiency=.94,discharge_efficiency=.95,base_bus_power_w=12,science_increment_w=18,downlink_increment_w=12,heater_increment_w=8,solar_rated_power_w=70,solar_reference_irradiance_w_m2=1361,array_normal_body_unit=[0,0,1])
profile['mobility'].update(response_model_id='r1-declared-baseline',response_model_version='0.1.0',response_model_kind='declared_constant',nominal_speed_m_s=.05,max_supported_slope_deg=20,driving_bus_power_w=32,validity_domain={'slope_min_deg':-20,'slope_max_deg':20,'speed_min_m_s':.01,'speed_max_m_s':.1,'soil_categories':['assumed_firm','assumed_loose']})
profile['provenance']['notes']='Hypothetical Clavius reference rover. Mass, battery, array and mobility inputs are declared engineering assumptions, not measured flight hardware or calibrated lunar performance.'
(out/'clavius-r1.urdf').write_text(body)
(out/'clavius-r1-profile.json').write_text(json.dumps(profile,indent=2)+'\n')
with zipfile.ZipFile(out/'clavius-r1.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name,value in [('clavius-r1.urdf',body),('clavius-profile.json',json.dumps(profile,indent=2))]:
  item=zipfile.ZipInfo(name,date_time=(2026,11,14,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;z.writestr(item,value)
print('Reference URDF, profile and package written.')
