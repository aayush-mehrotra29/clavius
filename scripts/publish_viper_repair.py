"""Rescore and publish complete adapted-model evidence, retaining negative cases."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

import numpy as np

from planner.validation.scm import ROOT,digest
from planner.validation.viper_frames import PROTOCOL,score_frame,verified_runtime
from scripts.benchmark_viper_rigid import PROTOCOL as RIGID_PROTOCOL,summarize as score_rigid


def verify(directory):
    directory=directory.resolve();runtime=verified_runtime()
    r=json.loads((directory/'report.json').read_text())
    policy=json.loads(PROTOCOL.read_text());rigid_policy=json.loads(RIGID_PROTOCOL.read_text())
    if r['runtime_identity']!=runtime['runtime_identity'] or r['protocol_sha256']!=digest(PROTOCOL) or r['rigid_protocol_sha256']!=digest(RIGID_PROTOCOL):
        raise ValueError('Executed model/protocol identities differ')
    for item in json.loads((directory/'evidence-index.json').read_text()):
        file=directory/item['file']
        if not file.resolve().is_relative_to(directory) or digest(file)!=item['sha256']:raise ValueError('Retained evidence differs: '+item['file'])
    expected=[(case['variant']+'-'+case['mode']+'-'+pose,case,pose) for case in policy['frame_cases'] for pose in policy['poses']]
    if [row['case'] for row in r['frame_cases']]!=[item[0] for item in expected]:raise ValueError('Frame matrix incomplete')
    for row,(stem,case,pose) in zip(r['frame_cases'],expected,strict=True):
        file=directory/stem/'native.json';raw=json.loads(file.read_text())
        variant='upstream-original' if case['variant']=='original' else 'clavius-frame-repaired'
        if raw['variant']!=variant or raw['mode']!=case['mode'] or raw['pose']!=pose or digest(file)!=row['raw_sha256']:
            raise ValueError('Frame input/output binding differs')
        scored=score_frame(raw,policy)
        if any(row[key]!=value for key,value in scored.items()):raise ValueError('Rescored frame metrics differ')
        check_invocation(directory/stem,runtime,'frames_'+case['variant'],[ROOT/'data/raw/robots/chrono/data',case['mode'],pose,file])
    expected_floor=['rigid-'+label+'-'+kind for label in ['earth','moon'] for kind in ['base','refined']]
    if [row['case'] for row in r['rigid_cases']]!=expected_floor:raise ValueError('Floor matrix incomplete')
    for row in r['rigid_cases']:
        folder=directory/row['case'];trace=folder/'trace.csv'
        if digest(trace)!=row['trace_sha256']:raise ValueError('Native floor trace differs')
        gravity=rigid_policy['gravity_cases_m_s2'][['earth','moon'].index(row['label'])]
        dt=rigid_policy['base_dt_s'] if row['kind']=='base' else rigid_policy['refined_dt_s']
        if row['gravity_m_s2']!=gravity or row['dt_s']!=dt:raise ValueError('Floor conditions differ')
        scored=score_rigid(np.genfromtxt(trace,names=True,delimiter=','),gravity,dt,rigid_policy)
        if any(row[key]!=value for key,value in scored.items()):raise ValueError('Rescored floor evidence differs')
        check_invocation(folder,runtime,'rigid_repaired',[ROOT/'data/raw/robots/chrono/data',gravity,dt,trace])
    if [row['label'] for row in r['rigid_refinements']]!=['earth','moon']:raise ValueError('Floor refinement matrix incomplete')
    for refinement in r['rigid_refinements']:
        base,fine=[row for row in r['rigid_cases'] if row['label']==refinement['label']]
        speed=fine['mean_speed_m_s']-base['mean_speed_m_s']
        position=float(np.linalg.norm(np.asarray(fine['final_position_m'])-np.asarray(base['final_position_m'])))
        normal=abs(fine['mean_normal_force_n']-base['mean_normal_force_n'])/base['nominal_weight_n']
        if refinement['mean_speed_change_m_s']!=speed or refinement['final_position_change_m']!=position or refinement['normal_load_change_fraction']!=normal:raise ValueError('Refinement metrics differ')
        c=rigid_policy['checks']
        checks={'speed':abs(speed)<=c['maximum_refined_speed_change_m_s'],'final_position':position<=c['maximum_refined_final_position_change_m'],'normal_load':normal<=c['maximum_refined_normal_load_change_fraction']}
        if refinement['checks']!=checks or refinement['checks_passed']!=all(checks.values()):raise ValueError('Refinement acceptance differs')
    original=[row for row in r['frame_cases'] if row['variant']=='upstream-original']
    repaired=[row for row in r['frame_cases'] if row['variant']=='clavius-frame-repaired' and row['mode']!='wrong-axis']
    negative=[row for row in r['frame_cases'] if row['mode']=='wrong-axis']
    baseline=len(original)==4 and all(not row['checks']['collider_cog_frames'] and not row['checks']['total_mass_accounting'] for row in original)
    rejected=len(negative)==2 and all(not row['checks']['shaft_reference_directions'] and row['forward_wheel_speeds_rad_s'][0]<0 and row['forward_wheel_speeds_rad_s'][2]<0 and row['forward_wheel_speeds_rad_s'][1]>0 and row['forward_wheel_speeds_rad_s'][3]>0 for row in negative)
    frame_ok=len(repaired)==4 and all(row['checks_passed'] for row in repaired) and baseline and rejected
    rigid_ok=all(row['checks_passed'] for row in r['rigid_cases']+r['rigid_refinements'])
    expected_acceptance={'repaired_frame_targets_met':frame_ok,'baseline_defects_reproduced':baseline,'deliberate_axis_error_detected':rejected,'rigid_targets_met':rigid_ok}
    if any(r[key]!=value for key,value in expected_acceptance.items()):raise ValueError('Component acceptance differs from numerical evidence')
    if not all(expected_acceptance.values()):
        raise ValueError('Repair acceptance is incomplete or failed')
    if r['active_app_robot'] or r['flight_prediction_validated'] or r['lunar_soil_validated']:raise ValueError('Unsupported hardware validation claim')
    return r


def check_invocation(folder,runtime,kind,arguments):
    inv=json.loads((folder/'invocation.json').read_text())
    expected=ROOT/runtime['executables'][kind]
    if inv['state']!='completed' or inv['returncode']!=0 or inv['runtime_identity']!=runtime['runtime_identity'] or inv['command']!=[str(expected),*map(str,arguments)] or inv['protocol_sha256']!=digest(PROTOCOL) or inv['executable_sha256']!=digest(expected):
        raise ValueError('Native invocation identity differs')


def publish(directory):
    r=verify(directory)
    archive=directory.with_suffix('.zip')
    r['evidence']={'directory':str(directory.relative_to(ROOT)),'report_sha256':digest(directory/'report.json'),'index_sha256':digest(directory/'evidence-index.json'),'archive':str(archive.relative_to(ROOT)),'archive_sha256':digest(archive),'archive_bytes':archive.stat().st_size}
    r['postrun_reverification']={'verified_utc':datetime.now(timezone.utc).isoformat(),'cases_rescored':14,'all_native_results_unchanged':True,'scorer_sha256':digest(ROOT/'planner/validation/viper_frames.py'),'verifier_sha256':digest(Path(__file__)),'note':'After native execution, evidence guards were tightened for nonfinite clocks/shaft data, negative residuals and explicit case bindings. All actual finite native metrics rescore identically; the originally executed source snapshots remain in the archive.'}
    target=ROOT/'docs/validation/viper-frame-repair.json';target.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'published':str(target),'repaired_frame_targets_met':True,'rigid_targets_met':True,'flight_prediction_validated':False}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    publish(p.parse_args().directory.resolve())
