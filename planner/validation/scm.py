"""Isolated Chrono SCM cases and frozen calibration protocol.

This module does not replace app rover dynamics or claim lunar calibration.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name('scm_protocol.json')
RUNTIME = ROOT / 'data/runtime/chrono-runtime.json'


def digest(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            h.update(chunk)
    return h.hexdigest()


def protocol():
    record=json.loads(PROTOCOL.read_text())
    source=ROOT/'public/data/mobility-reference.json'
    if digest(source)!=record['source_reference_sha256']:
        raise ValueError('SCM protocol refers to a different published reference')
    reference=json.loads(source.read_text())
    points=next(series['points'] for series in reference['series'] if series['id']=='trec-grc3-vv')
    train,holdout=record['training_source_indices'],record['holdout_source_indices']
    if set(train)&set(holdout) or sorted(train+holdout)!=list(range(len(points))):
        raise ValueError('Training/holdout split must partition the original points')
    return record,points


def configuration(slip,friction_angle=30.,janosi=.015,dt=None,grid=None,duration=None):
    p,_=protocol()
    return {**p['fixed_material_assumptions'],'slip':float(slip),'friction_angle_deg':float(friction_angle),'janosi_m':float(janosi),'dt_s':p['base_dt_s'] if dt is None else dt,'grid_m':p['base_grid_m'] if grid is None else grid,'duration_s':p['duration_s'] if duration is None else duration,'gravity_m_s2':p['gravity_m_s2']}


def verified_runtime():
    record=json.loads(RUNTIME.read_text())
    if record['version']!='9.0.1' or record['upstream_commit']!='2617649bf687456328a122b63dc0bb64df91394a':
        raise ValueError('Unsupported native Chrono release')
    for item in record['files']:
        file=ROOT/item['file']
        if not file.resolve().is_relative_to(ROOT) or digest(file)!=item['sha256']:
            raise ValueError('Chrono runtime differs: '+item['file'])
    content={key:record[key] for key in ['version','upstream_commit','files','compiler','configuration_sha256']}
    identity=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if identity!=record['runtime_identity']:
        raise ValueError('Chrono runtime inventory identity differs')
    return ROOT/record['executable'],record


def summarize(trace,config,checks=None):
    if trace.dtype.names is None or len(trace)<2:
        raise ValueError('Missing native SCM telemetry')
    required=['time_s','x_m','z_m','vx_m_s','vz_m_s','omega_rad_s','terrain_force_x_n','terrain_force_z_n','terrain_torque_y_nm','linear_motor_force_n','spin_motor_torque_nm','center_sinkage_m','center_plastic_sinkage_m','ray_hits']
    if list(trace.dtype.names)!=required:
        raise ValueError('SCM telemetry columns differ')
    if any(not np.isfinite(trace[name]).all() for name in required):
        raise ValueError('Nonfinite native SCM telemetry')
    t=trace['time_s']
    if not np.all(np.diff(t)>0) or abs(t[-1]-config['duration_s'])>config['dt_s']*.01:
        raise ValueError('Incomplete or unordered native SCM clock')
    p,_=protocol(); limits=checks or p['checks']
    start,end=p['steady_window_s']
    if config['duration_s']<end:
        raise ValueError('A complete steady window is required for assessment')
    mask=(t>=start)&(t<=end+1e-8)
    if mask.sum()<100:
        raise ValueError('Insufficient steady-window samples')
    # Time integration avoids bias from a final shortened sample interval.
    times=t[mask]
    def average(name):
        return float(np.trapezoid(trace[name][mask],times)/(times[-1]-times[0]))
    speed,omega=average('vx_m_s'),average('omega_rad_s')
    target_omega=.2/(.25*(1-config['slip']))
    load=17.5*config['gravity_m_s2']
    force_x,force_z=average('terrain_force_x_n'),average('terrain_force_z_n')
    control={
        'translation_tracking':abs(speed-.2)<=limits['maximum_translation_error_m_s'],
        'angular_velocity_tracking':abs(omega-target_omega)/target_omega<=limits['maximum_relative_angular_speed_error'],
        'normal_load':abs(force_z-load)/load<=limits['maximum_relative_normal_load_error'],
        'vertically_settled':abs(average('vz_m_s'))<=limits['maximum_abs_mean_vertical_velocity_m_s'],
    }
    return {'mean_translation_m_s':speed,'mean_omega_rad_s':omega,'mean_actual_slip_fraction':1-speed/(omega*.25),'mean_terrain_force_x_n':force_x,'mean_normal_force_n':force_z,'nominal_normal_load_n':load,'mean_traction_slope_deg':math.degrees(math.atan(force_x/load)),'mean_reported_linear_reaction_n':average('linear_motor_force_n'),'mean_reported_spin_reaction_nm':average('spin_motor_torque_nm'),'mean_wheel_center_z_m':average('z_m'),'mean_center_sinkage_m':average('center_sinkage_m'),'mean_center_plastic_sinkage_m':average('center_plastic_sinkage_m'),'controls':control,'controls_passed':all(control.values()),'steady_sample_count':int(mask.sum()),'actual_steady_interval_s':[float(times[0]),float(times[-1])],'reference_gravity_matches':config['gravity_m_s2']==p['gravity_m_s2'],'lunar_validation_established':False}


def run_case(config,output,timeout=300,cancel=lambda:False):
    executable,runtime=verified_runtime()
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    input_file=output/'input.json'
    input_file.write_text(json.dumps(config,indent=2,allow_nan=False)+'\n')
    invocation={'started_utc':datetime.now(timezone.utc).isoformat(),'runtime_identity':runtime['runtime_identity'],'input_sha256':digest(input_file),'protocol_sha256':digest(PROTOCOL),'command':[str(executable),str(input_file),str(output/'trace.csv')]}
    (output/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    started=time.monotonic()
    with (output/'native.log').open('w') as log:
        process=subprocess.Popen(invocation['command'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        state='running'
        while process.poll() is None:
            cancelled=cancel()
            if cancelled or time.monotonic()-started>timeout:
                state='cancelled' if cancelled else 'timed_out'
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                break
            try:process.wait(timeout=.1)
            except subprocess.TimeoutExpired:pass
    invocation.update(returncode=process.returncode,state=state if state!='running' else 'completed' if process.returncode==0 else 'failed',elapsed_wall_s=time.monotonic()-started)
    (output/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    if invocation['state']!='completed':
        raise RuntimeError('Native SCM case '+invocation['state']+'; evidence retained at '+str(output))
    trace=np.genfromtxt(output/'trace.csv',delimiter=',',names=True)
    result=summarize(trace,config)
    result.update(configuration=config,runtime_identity=runtime['runtime_identity'],input_sha256=digest(input_file),trace_sha256=digest(output/'trace.csv'))
    (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result
