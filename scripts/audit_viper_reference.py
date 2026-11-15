"""Audit Chrono's VIPER model against a dated NASA hardware reference.

This builds a separate inspection executable, leaves upstream source unchanged,
and does not enable a flight-rover model in the app.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

from planner.validation.scm import ROOT,digest,verified_runtime

SOURCE=ROOT/'data/raw/robots/chrono'
HARDWARE=ROOT/'data/raw/robots/research/viper-mobility-hardware-2024.pdf'
HARDWARE_SHA='fde1179cbf7af0fa04bdf4d19bb2c133a6c551e616fa921bb69354c21ec18465'


def audit(output):
    _,runtime=verified_runtime()
    if digest(HARDWARE)!=HARDWARE_SHA:
        raise ValueError('NASA hardware reference changed')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    build=ROOT/'data/runtime/chrono-model-audit-build'
    cmake=str(ROOT/'data/runtime/chrono-deps/bin/cmake')
    commands=[[cmake,'-S',str(ROOT/'workers/chrono/model-audit'),'-B',str(build),'-DChrono_DIR='+str(ROOT/'data/runtime/chrono-build/cmake'),'-DCMAKE_BUILD_TYPE=Release'],[cmake,'--build',str(build),'--parallel','1']]
    with (output/'build.log').open('w') as log:
        for command in commands:
            subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    executable=build/'clavius_viper_audit'
    command=[str(executable),str(SOURCE/'data'),str(output/'native-model.json')]
    with (output/'native.log').open('w') as log:
        subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=60)
    native=json.loads((output/'native-model.json').read_text())
    frame_executable=build/'clavius_viper_wheel_mass_frames'
    frame_command=[str(frame_executable),str(SOURCE/'data/robot/viper/col/viper_wheel.obj'),str(output/'wheel-mass-frames.json')]
    subprocess.run(frame_command,check=True,timeout=60)
    frames=json.loads((output/'wheel-mass-frames.json').read_text())
    frame_offsets={}
    for body in native['bodies']:
        if not body['name'].startswith('wheel_'):continue
        side='left_rotated_collider' if body['name'] in ['wheel_LF_body','wheel_LB_body'] else 'right_collider'
        expected=np.asarray(frames[side]['cog_relative_reference_m'])
        actual=np.asarray(body['com_relative_reference_m'])
        frame_offsets[body['name']]={'collider_cog_m':expected.tolist(),'body_cog_m':actual.tolist(),'difference_m':(actual-expected).tolist(),'distance_m':float(np.linalg.norm(actual-expected))}
    frame_consistency={'role':'Consistency of source-derived mass frames with the actual collider; not measured NASA flight COG','tolerance_m':1e-6,'wheel_offsets':frame_offsets,'checks_passed':all(row['distance_m']<=1e-6 for row in frame_offsets.values()),'native_geometry':frames,'command':frame_command,'native_output_sha256':digest(output/'wheel-mass-frames.json')}
    cpp=SOURCE/'src/chrono_models/robot/viper/Viper.cpp'
    source=cpp.read_text()
    if not re.search(r'm_max_steer_angle\s*=\s*CH_PI\s*/\s*6\s*;',source):
        raise ValueError('Upstream steering implementation changed; re-audit it')
    masses=np.array([body['mass_kg'] for body in native['bodies']])
    inertias=np.array([body['inertia_com_principal_kg_m2'] for body in native['bodies']])
    checks={
        'all_masses_positive':bool(np.isfinite(masses).all() and (masses>0).all()),
        'all_principal_inertias_positive':bool(np.isfinite(inertias).all() and (inertias>0).all()),
        'inertia_triangle_inequalities':bool((2*inertias.max(axis=1)<=inertias.sum(axis=1)+1e-9).all()),
        'sum_matches_actual_system_mass':math.isclose(float(masses.sum()),native['all_body_mass_kg'],abs_tol=1e-9),
        'four_wheels_present':sum(body['name'].startswith('wheel_') for body in native['bodies'])==4,
    }
    vertices=np.array([[float(value) for value in line.split()[1:4]] for line in (SOURCE/'data/robot/viper/col/viper_wheel.obj').read_text().splitlines() if line.startswith('v ')])
    wheel_geometry={'maximum_radial_extent_about_y_m':float(np.hypot(vertices[:,0],vertices[:,2]).max()),'full_y_extent_m':float(np.ptp(vertices[:,1])),'role':'Upstream collider bounds, including protrusions; not measured flight-wheel width or the separate TREC fixture.'}
    source_files=[cpp,SOURCE/'src/chrono_models/robot/viper/Viper.h',SOURCE/'LICENSE',*sorted((SOURCE/'data/robot/viper/col').glob('*.obj')),*[ROOT/item['file'] for item in runtime['files'] if item['file'].endswith('.dylib')],executable,frame_executable,ROOT/'workers/chrono/model-audit/viper.cpp',ROOT/'workers/chrono/model-audit/wheel-mass-frames.cpp',ROOT/'workers/chrono/model-audit/CMakeLists.txt',Path(__file__).resolve()]
    files=[{'file':str(file.relative_to(ROOT)),'sha256':digest(file),'bytes':file.stat().st_size} for file in source_files]
    report={
        'id':'clavius-viper-upstream-audit-v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
        'role':'Candidate model audit; not active app robot support or flight validation',
        'software':{'name':'Project Chrono','version':'9.0.1','upstream_commit':runtime['upstream_commit'],'repository':runtime['source_repository'],'reference_runtime_identity':runtime['runtime_identity']},
        'hardware_reference':{'title':'VIPER Rover Overview and Mobility and Hardware','author':'Bill Bluethmann','presentation_date':'2024-11-14','url':'https://ntrs.nasa.gov/citations/20240013903','download_url':'https://ntrs.nasa.gov/api/citations/20240013903/downloads/LSIC_2024-Tech%20Infusion_Panel-VIPER_Mob-HW.pdf','sha256':HARDWARE_SHA,'bytes':HARDWARE.stat().st_size,'facts':{
            'roving_mass_kg':{'value':447,'page':2},'launch_mass_with_lander_interface_kg':{'value':490,'page':2},
            'envelope_m':{'value':[1.7,1.7,2.5],'page':2},
            'battery_capacity_wh':{'value':5420,'condition':'Start of life at 0 degrees C; not a temperature-dependent discharge curve','page':2},
            'solar_panel_w':{'value':320,'condition':'Published panel output; not a mission-time incidence/temperature efficiency model','page':2},
            'wheel_diameter_m':{'value':.5,'page':4},'grouser_height_m':{'value':.025,'page':4},
            'top_speed_m_s':{'value':.2,'page':4},'nominal_speed_m_s':{'value':.1,'page':4},
            'steering_half_range_deg':{'value':50,'page':4},'ground_clearance_range_m':{'value':[.07,.43],'page':4},
            'slope_requirement_deg':{'value':15,'role':'Design requirement, not demonstrated Clavius performance','page':4},
            'obstacle_requirement_m':{'value':.15,'role':'Design requirement, not guaranteed traversability','page':4},
        }},
        'native_model':native,'structural_checks':checks,'wheel_collider_geometry':wheel_geometry,'mass_frame_consistency':frame_consistency,
        'differences':{
            'mass_difference_from_roving_reference_kg':native['all_body_mass_kg']-447,
            'mass_difference_from_roving_reference_percent':100*(native['all_body_mass_kg']/447-1),
            'mass_excluded_by_upstream_getter_kg':native['all_body_mass_kg']-native['upstream_rover_mass_getter_kg'],
            'upstream_steering_half_range_deg':30,'hardware_steering_half_range_deg':50,
        },
        'assumption_ledger':[
            'Body masses and principal inertias derive from collider mesh volumes with assumed part densities; no measured flight tensors.',
            'Four 1 kg steering connector bodies contribute to system mass but are excluded by the upstream GetRoverMass helper.',
            'Upstream steering clamps to 30 degrees, below the dated hardware 50 degree range; no adaptation has been accepted.',
            'Upstream suspension springs use 800000 N/m and 10000 N s/m; these are source model values, not measured flight suspension curves.',
            'Upstream default DC driver uses 300 N m stall torque and pi rad/s no-load speed; no flight torque/current map is established.',
            'The flight hardware uses active wheel downforce and IMU control; those flight control loops have not been reproduced or validated.',
            'The native collider lateral extent is not interchangeable with the 0.2 m TREC laboratory wheel width.',
            'Left-wheel collider rotation is assigned after the upstream constructor computes mass properties. The native geometry check detects a COG-frame mismatch; reconcile it before adapting the model.',
            'The 5420 W h source capacity alone does not supply calibrated energy consumption, thermal or BMS response.',
        ],
        'active_app_model':False,'flight_prediction_validated':False,'lunar_soil_validated':False,
        'evidence':{'command':command,'native_output_sha256':digest(output/'native-model.json'),'files':files},
    }
    (output/'audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for file in [ROOT/'workers/chrono/model-audit/viper.cpp',ROOT/'workers/chrono/model-audit/wheel-mass-frames.cpp',ROOT/'workers/chrono/model-audit/CMakeLists.txt',Path(__file__).resolve()]:
        shutil.copyfile(file,output/file.name)
    print(json.dumps({'structural_checks':checks,'differences':report['differences'],'mass_frame_consistency':frame_consistency['checks_passed'],'wheel_frame_offsets_m':{name:row['distance_m'] for name,row in frame_offsets.items()},'active_app_model':False}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    audit(parser.parse_args().output)
