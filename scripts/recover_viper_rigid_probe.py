"""Retain three complete probes and retry only the wall-limited lunar half-step.

The native model, numerical step and predeclared gates are unchanged. Imported
traces are rescored; their original invocation records remain explicit.
"""
import argparse
import ast
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from planner.validation.scm import ROOT,digest,verified_runtime
from scripts.benchmark_viper_rigid import PROTOCOL,summarize


def recover(previous,output):
    _,runtime=verified_runtime()
    previous=previous.resolve();output=output.resolve()
    if digest(previous/'protocol.json')!=digest(PROTOCOL):raise ValueError('Probe protocol changed')
    for file,original in [('viper-rigid.cpp',ROOT/'workers/chrono/rover-probe/viper-rigid.cpp'),('CMakeLists.txt',ROOT/'workers/chrono/rover-probe/CMakeLists.txt')]:
        if digest(previous/file)!=digest(original):raise ValueError('Executed probe source changed')
    def scoring_ast(file):
        tree=ast.parse(file.read_text())
        return ast.dump(next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='summarize'),include_attributes=False)
    if scoring_ast(previous/'benchmark_viper_rigid.py')!=scoring_ast(ROOT/'scripts/benchmark_viper_rigid.py'):
        raise ValueError('Probe scoring changed; review before recovery')
    old_runtime=json.loads((previous/'runtime.json').read_text())
    if runtime['runtime_identity']!=old_runtime['runtime_identity']:raise ValueError('Probe native libraries changed')
    completed=json.loads((previous/'checkpoint.json').read_text())['cases']
    if [(row['label'],row['kind']) for row in completed]!=[('earth','base'),('earth','refined'),('moon','base')]:raise ValueError('This recovery requires exactly the three retained complete cases')
    output.mkdir(parents=True,exist_ok=False)
    policy=json.loads(PROTOCOL.read_text())
    cases=[]
    for row in completed:
        stem=row['label']+'-'+row['kind']
        trace=previous/(stem+'.csv')
        if digest(trace)!=row['trace_sha256']:raise ValueError('Retained native trace differs')
        scored=summarize(np.genfromtxt(trace,delimiter=',',names=True),row['gravity_m_s2'],row['dt_s'],policy)
        if any(row[key]!=value for key,value in scored.items()):raise ValueError('Retained native score differs')
        invocation=json.loads((previous/(stem+'-invocation.json')).read_text())
        if invocation['returncode']!=0 or invocation['protocol_sha256']!=digest(PROTOCOL) or invocation['reference_runtime_identity']!=runtime['runtime_identity']:raise ValueError('Retained invocation differs')
        for suffix in ['.csv','.log','-invocation.json']:shutil.copyfile(previous/(stem+suffix),output/(stem+suffix))
        cases.append(row)
    for name in ['runtime.json','protocol.json','benchmark_viper_rigid.py','viper-rigid.cpp','CMakeLists.txt']:shutil.copyfile(previous/name,output/name)
    shutil.copyfile(Path(__file__),output/Path(__file__).name)
    executable=ROOT/'data/runtime/chrono-rover-probe-build/clavius_viper_rigid_probe'
    paths=[executable,PROTOCOL,ROOT/'workers/chrono/rover-probe/viper-rigid.cpp',ROOT/'workers/chrono/rover-probe/CMakeLists.txt',Path(__file__).resolve(),*sorted((ROOT/'data/raw/robots/chrono/data/robot/viper/col').glob('*.obj'))]
    pins=[{'file':str(file.relative_to(ROOT)),'sha256':digest(file),'bytes':file.stat().st_size} for file in paths]
    command=[str(executable),str(ROOT/'data/raw/robots/chrono/data'),'1.62','0.0005',str(output/'moon-refined.csv')]
    invocation={'started_utc':datetime.now(timezone.utc).isoformat(),'command':command,'reference_runtime_identity':runtime['runtime_identity'],'protocol_sha256':digest(PROTOCOL),'executable_sha256':digest(executable),'wall_limit_s':900,'state':'running'}
    inv_file=output/'moon-refined-invocation.json';inv_file.write_text(json.dumps(invocation,indent=2)+'\n')
    started=time.monotonic()
    try:
        with (output/'moon-refined.log').open('w') as log:result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    except subprocess.TimeoutExpired:
        invocation.update(state='timed_out',elapsed_wall_s=time.monotonic()-started)
        inv_file.write_text(json.dumps(invocation,indent=2)+'\n');raise
    invocation.update(state='completed' if result.returncode==0 else 'failed',returncode=result.returncode,elapsed_wall_s=time.monotonic()-started)
    inv_file.write_text(json.dumps(invocation,indent=2)+'\n')
    if result.returncode!=0:raise RuntimeError('Retried native probe failed; evidence retained')
    for item in pins:
        if digest(ROOT/item['file'])!=item['sha256']:raise ValueError('Probe input changed during recovery')
    row=summarize(np.genfromtxt(output/'moon-refined.csv',delimiter=',',names=True),1.62,.0005,policy)
    row.update(label='moon',kind='refined',trace_sha256=digest(output/'moon-refined.csv'));cases.append(row)
    refinements=[];c=policy['checks']
    for label in ['earth','moon']:
        base,fine=[row for row in cases if row['label']==label]
        speed_change=fine['mean_speed_m_s']-base['mean_speed_m_s']
        position_change=float(np.linalg.norm(np.asarray(fine['final_position_m'])-np.asarray(base['final_position_m'])))
        normal_change=abs(fine['mean_normal_force_n']-base['mean_normal_force_n'])/base['nominal_weight_n']
        checks={'speed':abs(speed_change)<=c['maximum_refined_speed_change_m_s'],'final_position':position_change<=c['maximum_refined_final_position_change_m'],'normal_load':normal_change<=c['maximum_refined_normal_load_change_fraction']}
        refinements.append({'label':label,'mean_speed_change_m_s':speed_change,'final_position_change_m':position_change,'normal_load_change_fraction':normal_change,'checks':checks,'checks_passed':all(checks.values())})
    previous_archive=previous.with_suffix('.zip')
    report={'id':policy['id'],'recorded_utc':datetime.now(timezone.utc).isoformat(),'protocol':policy,'reference_runtime_identity':runtime['runtime_identity'],'evidence_files':pins,'cases':cases,'refinements':refinements,'component_targets_met':all(row['checks_passed'] for row in cases+refinements),'active_app_robot':False,'flight_prediction_validated':False,'lunar_soil_validated':False,'limits':policy['limits'],'recovery':{'previous_archive':str(previous_archive.relative_to(ROOT)),'previous_archive_sha256':digest(previous_archive),'imported_completed_cases':3,'repeated_case':'moon-refined','change':'Only wall-clock allowance from 300 to 900 seconds; native model, numerical settings and criteria unchanged.','original_timeout':json.loads((previous/'moon-refined-timeout.json').read_text()),'identity_record_limit':'Original completed cases retain their library-runtime/command/trace identities; the probe executable hash was first retained by this recovery, not retroactively claimed at their launches.'}}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'component_targets_met':report['component_targets_met'],'refinements':refinements,'flight_prediction_validated':False}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('previous',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();recover(args.previous,args.output)
