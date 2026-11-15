"""Execute preserved baseline, repaired model and deliberate wrong-axis cases."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np

from planner.validation.scm import ROOT, digest
from planner.validation.viper_frames import PROTOCOL, INVENTORY, execute, score_frame, verified_runtime
from scripts.benchmark_viper_rigid import PROTOCOL as RIGID_PROTOCOL, summarize as score_rigid


def save(file, value):
    file.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def validate(output):
    runtime = verified_runtime()
    p = json.loads(PROTOCOL.read_text())
    rigid_p = json.loads(RIGID_PROTOCOL.read_text())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = [PROTOCOL, RIGID_PROTOCOL, ROOT/'planner/validation/viper_frames.py', ROOT/'scripts/benchmark_viper_rigid.py', Path(__file__).resolve()]
    pins = {str(file.relative_to(ROOT)): digest(file) for file in inputs}
    save(output/'input-pins.json', pins)
    shutil.copyfile(PROTOCOL, output/'protocol.json')
    shutil.copyfile(RIGID_PROTOCOL, output/'rigid-protocol.json')
    shutil.copyfile(INVENTORY, output/'runtime.json')
    for file in [ROOT/'workers/chrono/viper-adapted/model.json', ROOT/'workers/chrono/viper-adapted/model.patch', ROOT/'workers/chrono/viper-adapted/CMakeLists.txt', ROOT/'workers/chrono/viper-adapted/frames.cpp', *inputs[2:]]:
        shutil.copyfile(file, output/file.name)
    for file in (ROOT/'data/runtime/viper-adapted-source').rglob('*'):
        if file.is_file():
            target=output/'generated-source'/file.relative_to(ROOT/'data/runtime/viper-adapted-source')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
    def check_inputs():
        for file, expected in pins.items():
            if digest(ROOT/file)!=expected:raise ValueError('Validation input changed during execution: '+file)
    frames=[]
    for case in p['frame_cases']:
        for pose in p['poses']:
            check_inputs()
            stem=case['variant']+'-'+case['mode']+'-'+pose
            directory=output/stem;result=directory/'native.json'
            executable=ROOT/runtime['executables']['frames_'+case['variant']]
            execute(executable,[ROOT/'data/raw/robots/chrono/data',case['mode'],pose,result],directory,runtime,timeout=60)
            raw=json.loads(result.read_text())
            expected_variant='upstream-original' if case['variant']=='original' else 'clavius-frame-repaired'
            if raw['variant']!=expected_variant or raw['mode']!=case['mode'] or raw['pose']!=pose:
                raise ValueError('Native frame response differs from the launched case')
            scored=score_frame(raw,p)
            scored.update(case=stem,raw_sha256=digest(result));frames.append(scored)
            save(directory/'assessment.json',scored)
            save(output/'checkpoint.json',{'stage':'frames','frames':frames})
            print(json.dumps({'stage':'frames','case':stem,'checks_passed':scored['checks_passed'],'checks':scored['checks']}),flush=True)
    repaired=[row for row in frames if row['variant']=='clavius-frame-repaired' and row['mode']!='wrong-axis']
    original=[row for row in frames if row['variant']=='upstream-original']
    negative=[row for row in frames if row['mode']=='wrong-axis']
    baseline_reproduced=len(original)==4 and all(not row['checks']['collider_cog_frames'] and not row['checks']['total_mass_accounting'] for row in original)
    negative_detected=len(negative)==2 and all(not row['checks']['shaft_reference_directions'] and row['forward_wheel_speeds_rad_s'][0]<0 and row['forward_wheel_speeds_rad_s'][2]<0 and row['forward_wheel_speeds_rad_s'][1]>0 and row['forward_wheel_speeds_rad_s'][3]>0 for row in negative)
    frames_passed=len(repaired)==4 and all(row['checks_passed'] for row in repaired) and baseline_reproduced and negative_detected
    floor=[];refinements=[]
    if frames_passed:
        for label,gravity in zip(['earth','moon'],rigid_p['gravity_cases_m_s2'],strict=True):
            pair=[]
            for kind,dt in [('base',rigid_p['base_dt_s']),('refined',rigid_p['refined_dt_s'])]:
                check_inputs();stem='rigid-'+label+'-'+kind
                directory=output/stem;trace=directory/'trace.csv'
                execute(ROOT/runtime['executables']['rigid_repaired'],[ROOT/'data/raw/robots/chrono/data',gravity,dt,trace],directory,runtime)
                row=score_rigid(np.genfromtxt(trace,delimiter=',',names=True),gravity,dt,rigid_p)
                row.update(case=stem,label=label,kind=kind,trace_sha256=digest(trace));pair.append(row);floor.append(row)
                save(directory/'assessment.json',row);save(output/'checkpoint.json',{'stage':'rigid-floor','frames':frames,'floor':floor})
                print(json.dumps({'stage':'rigid-floor','case':stem,**row}),flush=True)
            base,fine=pair;c=rigid_p['checks']
            speed=fine['mean_speed_m_s']-base['mean_speed_m_s']
            position=float(np.linalg.norm(np.asarray(fine['final_position_m'])-np.asarray(base['final_position_m'])))
            normal=abs(fine['mean_normal_force_n']-base['mean_normal_force_n'])/base['nominal_weight_n']
            checks={'speed':abs(speed)<=c['maximum_refined_speed_change_m_s'],'final_position':position<=c['maximum_refined_final_position_change_m'],'normal_load':normal<=c['maximum_refined_normal_load_change_fraction']}
            refinements.append({'label':label,'mean_speed_change_m_s':speed,'final_position_change_m':position,'normal_load_change_fraction':normal,'checks':checks,'checks_passed':all(checks.values())})
    check_inputs();verified_runtime()
    report={'id':p['id'],'finished_utc':datetime.now(timezone.utc).isoformat(),'model_id':runtime['id'],'runtime_identity':runtime['runtime_identity'],'reference_runtime_identity':runtime['reference_runtime_identity'],'protocol_sha256':digest(PROTOCOL),'rigid_protocol_sha256':digest(RIGID_PROTOCOL),'frame_cases':frames,'baseline_defects_reproduced':baseline_reproduced,'deliberate_axis_error_detected':negative_detected,'repaired_frame_targets_met':frames_passed,'rigid_cases':floor,'rigid_refinements':refinements,'rigid_targets_met':len(floor)==4 and all(row['checks_passed'] for row in floor+refinements),'active_app_robot':False,'flight_prediction_validated':False,'lunar_soil_validated':False,'limitations':p['limitations']}
    save(output/'report.json',report)
    files=[{'file':str(file.relative_to(output)),'sha256':digest(file),'bytes':file.stat().st_size} for file in sorted(output.rglob('*')) if file.is_file()]
    save(output/'evidence-index.json',files)
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(output.rglob('*')):
            if file.is_file():bundle.write(file,file.relative_to(output))
    print(json.dumps({'repaired_frame_targets_met':frames_passed,'rigid_targets_met':report['rigid_targets_met'],'archive':str(archive),'sha256':digest(archive)}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    validate(parser.parse_args().output)
