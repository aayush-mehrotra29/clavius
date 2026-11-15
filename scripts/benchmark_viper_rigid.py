"""Bounded assembled upstream VIPER rigid-floor component probes."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from planner.validation.scm import ROOT,digest,verified_runtime

PROTOCOL=ROOT/'planner/validation/viper_rigid_protocol.json'
COLUMNS=['time_s','x_m','y_m','z_m','vx_m_s','vy_m_s','vz_m_s','normal_force_n','drive_torque_sum_nm','wheel_mean_omega_rad_s','chassis_qw','chassis_qx','chassis_qy','chassis_qz']


def summarize(trace,gravity,dt,policy):
    if trace.dtype.names is None or list(trace.dtype.names)!=COLUMNS or len(trace)<100:
        raise ValueError('Incomplete native rover telemetry')
    if any(not np.isfinite(trace[name]).all() for name in COLUMNS):
        raise ValueError('Nonfinite native rover telemetry')
    t=trace['time_s']
    if not (np.diff(t)>0).all() or abs(t[-1]-policy['duration_s'])>dt*.01:
        raise ValueError('Incomplete native rover simulation clock')
    window=(t>=policy['steady_window_s'][0])&(t<=policy['steady_window_s'][1]+1e-8)
    times=t[window]
    if len(times)<100:raise ValueError('Incomplete steady window')
    def mean(name):return float(np.trapezoid(trace[name][window],times)/(times[-1]-times[0]))
    mass=policy['nominal_rig_mass_kg'];load=mass*gravity
    q=np.array([trace['chassis_q'+axis] for axis in ['w','x','y','z']])
    quaternion_error=float(np.max(np.abs(np.linalg.norm(q,axis=0)-1)))
    lateral=float(np.max(np.abs(trace['y_m'][window])))
    c=policy['checks']
    checks={
        'speed_matches_wheel_envelope':abs(mean('vx_m_s')-policy['envelope_rolling_speed_m_s'])<=c['maximum_speed_difference_from_envelope_m_s'],
        'normal_load_balance':abs(mean('normal_force_n')/load-1)<=c['maximum_relative_normal_load_error'],
        'vertical_settling':abs(mean('vz_m_s'))<=c['maximum_abs_mean_vertical_speed_m_s'],
        'lateral_drift':lateral<=c['maximum_abs_lateral_position_m'],
        'quaternion_normalization':quaternion_error<=c['maximum_quaternion_norm_error'],
    }
    return {'gravity_m_s2':gravity,'dt_s':dt,'mean_speed_m_s':mean('vx_m_s'),'mean_vertical_speed_m_s':mean('vz_m_s'),'mean_normal_force_n':mean('normal_force_n'),'nominal_weight_n':load,'maximum_steady_lateral_position_m':lateral,'maximum_quaternion_norm_error':quaternion_error,'mean_wheel_omega_rad_s':mean('wheel_mean_omega_rad_s'),'final_position_m':[float(trace[axis+'_m'][-1]) for axis in ['x','y','z']],'checks':checks,'checks_passed':all(checks.values()),'flight_prediction_validated':False,'lunar_soil_validated':False}


def benchmark(output):
    _,runtime=verified_runtime()
    p=json.loads(PROTOCOL.read_text())
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    build=ROOT/'data/runtime/chrono-rover-probe-build'
    cmake=str(ROOT/'data/runtime/chrono-deps/bin/cmake')
    with (output/'build.log').open('w') as log:
        subprocess.run([cmake,'-S',str(ROOT/'workers/chrono/rover-probe'),'-B',str(build),'-DChrono_DIR='+str(ROOT/'data/runtime/chrono-build/cmake'),'-DCMAKE_BUILD_TYPE=Release'],check=True,stdout=log,stderr=subprocess.STDOUT)
        subprocess.run([cmake,'--build',str(build),'--parallel','1'],check=True,stdout=log,stderr=subprocess.STDOUT)
    executable=build/'clavius_viper_rigid_probe'
    source_files=[executable,PROTOCOL,ROOT/'workers/chrono/rover-probe/viper-rigid.cpp',ROOT/'workers/chrono/rover-probe/CMakeLists.txt',Path(__file__).resolve(),*sorted((ROOT/'data/raw/robots/chrono/data/robot/viper/col').glob('*.obj'))]
    pins=[{'file':str(file.relative_to(ROOT)),'sha256':digest(file),'bytes':file.stat().st_size} for file in source_files]
    shutil.copyfile(PROTOCOL,output/'protocol.json');shutil.copyfile(ROOT/'data/runtime/chrono-runtime.json',output/'runtime.json')
    (output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    for file in [ROOT/'workers/chrono/rover-probe/viper-rigid.cpp',ROOT/'workers/chrono/rover-probe/CMakeLists.txt',Path(__file__).resolve()]:shutil.copyfile(file,output/file.name)
    cases=[];refinements=[]
    for label,gravity in zip(['earth','moon'],p['gravity_cases_m_s2'],strict=True):
        pair=[]
        for kind,dt in [('base',p['base_dt_s']),('refined',p['refined_dt_s'])]:
            for item in pins:
                if digest(ROOT/item['file'])!=item['sha256']:raise ValueError('Rover probe input changed')
            verified_runtime()
            stem=label+'-'+kind
            command=[str(executable),str(ROOT/'data/raw/robots/chrono/data'),str(gravity),str(dt),str(output/(stem+'.csv'))]
            invocation={'started_utc':datetime.now(timezone.utc).isoformat(),'command':command,'reference_runtime_identity':runtime['runtime_identity'],'protocol_sha256':digest(PROTOCOL),'executable_sha256':digest(executable),'wall_limit_s':900,'state':'running'}
            inv_file=output/(stem+'-invocation.json')
            inv_file.write_text(json.dumps(invocation,indent=2)+'\n')
            started=time.monotonic()
            try:
                with (output/(stem+'.log')).open('w') as log:
                    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            except subprocess.TimeoutExpired:
                invocation.update(state='timed_out',elapsed_wall_s=time.monotonic()-started)
                inv_file.write_text(json.dumps(invocation,indent=2)+'\n');raise
            invocation.update(state='completed' if result.returncode==0 else 'failed',returncode=result.returncode,elapsed_wall_s=time.monotonic()-started)
            inv_file.write_text(json.dumps(invocation,indent=2)+'\n')
            if result.returncode!=0:raise RuntimeError('Native rover probe failed; evidence retained')
            row=summarize(np.genfromtxt(output/(stem+'.csv'),delimiter=',',names=True),gravity,dt,p)
            row.update(label=label,kind=kind,trace_sha256=digest(output/(stem+'.csv')))
            pair.append(row);cases.append(row)
            (output/'checkpoint.json').write_text(json.dumps({'cases':cases},indent=2)+'\n')
            print(json.dumps(row),flush=True)
        base,fine=pair;c=p['checks']
        speed_change=fine['mean_speed_m_s']-base['mean_speed_m_s']
        position_change=float(np.linalg.norm(np.asarray(fine['final_position_m'])-np.asarray(base['final_position_m'])))
        normal_change=abs(fine['mean_normal_force_n']-base['mean_normal_force_n'])/base['nominal_weight_n']
        checks={'speed':abs(speed_change)<=c['maximum_refined_speed_change_m_s'],'final_position':position_change<=c['maximum_refined_final_position_change_m'],'normal_load':normal_change<=c['maximum_refined_normal_load_change_fraction']}
        refinements.append({'label':label,'mean_speed_change_m_s':speed_change,'final_position_change_m':position_change,'normal_load_change_fraction':normal_change,'checks':checks,'checks_passed':all(checks.values())})
    report={'id':p['id'],'recorded_utc':datetime.now(timezone.utc).isoformat(),'protocol':p,'reference_runtime_identity':runtime['runtime_identity'],'evidence_files':pins,'cases':cases,'refinements':refinements,'component_targets_met':all(row['checks_passed'] for row in cases+refinements),'active_app_robot':False,'flight_prediction_validated':False,'lunar_soil_validated':False,'limits':p['limits']}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for file in [ROOT/'workers/chrono/rover-probe/viper-rigid.cpp',ROOT/'workers/chrono/rover-probe/CMakeLists.txt',Path(__file__).resolve()]:shutil.copyfile(file,output/file.name)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    report=benchmark(parser.parse_args().output)
    print(json.dumps({'component_targets_met':report['component_targets_met'],'flight_prediction_validated':False}),flush=True)
