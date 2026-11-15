"""Bounded frozen-split SCM development campaign, with retained failure evidence.

The source plotting coordinates remain unchanged. Only the predeclared parameter
candidates are ranked, exclusively on training groups. A frozen selection file
is written before holdout simulations begin.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import itertools
import json
from pathlib import Path
import shutil

import numpy as np

from planner.validation.scm import ROOT,PROTOCOL,configuration,digest,protocol,run_case,verified_runtime


def metrics(rows):
    errors=np.asarray([row['mean_traction_slope_deg']-row['published_traction_slope_deg'] for row in rows])
    return {'count':len(rows),'rmse_deg':float(np.sqrt(np.mean(errors**2))),'maximum_abs_error_deg':float(np.max(np.abs(errors))),'mean_bias_deg':float(errors.mean()),'controls_passed':all(row['controls_passed'] for row in rows)}


def save(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def campaign(output):
    p,points=protocol()
    _,runtime=verified_runtime()
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(PROTOCOL,output/'protocol.json')
    shutil.copyfile(ROOT/'public/data/mobility-reference.json',output/'published-reference.json')
    shutil.copyfile(ROOT/'data/runtime/chrono-runtime.json',output/'runtime.json')
    for file in [ROOT/'planner/validation/scm.py',ROOT/'workers/chrono/reference.cpp',Path(__file__)]:
        shutil.copyfile(file,output/file.name)
    # A campaign cannot combine results from silently changed protocols or
    # scoring code. Native/runtime files are additionally checked per case.
    inputs=[PROTOCOL,ROOT/'public/data/mobility-reference.json',ROOT/'planner/validation/scm.py',Path(__file__)]
    pinned_inputs={str(file.resolve()):digest(file) for file in inputs}
    save(output/'campaign-inputs.json',pinned_inputs)
    def checked_case(config,directory):
        for file,sha256 in pinned_inputs.items():
            if digest(file)!=sha256:
                raise ValueError('Campaign input changed during execution: '+file)
        return run_case(config,directory)
    started=datetime.now(timezone.utc).isoformat()
    candidates=[]
    variables=p['calibration_variables']
    for index,(phi,janosi) in enumerate(itertools.product(variables['friction_angle_deg'],variables['janosi_m'])):
        if index>=p['maximum_parameter_candidates']:break
        candidate={'index':index,'parameters':{'friction_angle_deg':phi,'janosi_m':janosi},'training':[]}
        for source_index in p['training_source_indices']:
            point=points[source_index]
            config=configuration(point['slip_fraction'],phi,janosi)
            result=checked_case(config,output/f'candidate-{index}/training-{source_index:02d}')
            result.update(source_index=source_index,published_traction_slope_deg=point['traction_slope_deg'])
            candidate['training'].append(result)
            print(json.dumps({'stage':'training','candidate':index,'source_index':source_index,'controls_passed':result['controls_passed'],'predicted_deg':result['mean_traction_slope_deg']}),flush=True)
            save(output/'checkpoint.json',{'stage':'training','completed_candidates':candidates,'current_candidate':candidate})
        candidate['training_metrics']=metrics(candidate['training'])
        candidates.append(candidate)
    eligible=[candidate for candidate in candidates if candidate['training_metrics']['controls_passed']]
    if not eligible:
        report={'status':'no_numerically_eligible_candidate','started_utc':started,'protocol_sha256':digest(PROTOCOL),'candidates':candidates,'holdout_evaluated':False,'lunar_validation_established':False}
        save(output/'campaign.json',report)
        return report
    best=min(eligible,key=lambda candidate:(candidate['training_metrics']['rmse_deg'],candidate['index']))
    selection={'selected_index':best['index'],'parameters':best['parameters'],'training_metrics':best['training_metrics'],'frozen_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':digest(PROTOCOL),'runtime_identity':runtime['runtime_identity'],'holdout_results_seen':False,'training_evidence_sha256':hashlib.sha256(json.dumps(candidates,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    save(output/'frozen-selection.json',selection)
    frozen_hash=digest(output/'frozen-selection.json')
    holdout=[]
    for source_index in p['holdout_source_indices']:
        point=points[source_index]
        result=checked_case(configuration(point['slip_fraction'],best['parameters']['friction_angle_deg'],best['parameters']['janosi_m']),output/f'holdout-{source_index:02d}')
        result.update(source_index=source_index,published_traction_slope_deg=point['traction_slope_deg'])
        holdout.append(result)
        save(output/'checkpoint.json',{'stage':'holdout','frozen_selection_sha256':frozen_hash,'candidates':candidates,'holdout':holdout})
        print(json.dumps({'stage':'holdout','source_index':source_index,'controls_passed':result['controls_passed'],'predicted_deg':result['mean_traction_slope_deg']}),flush=True)
    refinements=[]
    for source_index in p['numerical_refinement_source_indices']:
        point=points[source_index]
        base=next(row for row in best['training']+holdout if row['source_index']==source_index)
        for kind,dt,grid in [('time',p['refined_dt_s'],p['base_grid_m']),('grid',p['base_dt_s'],p['refined_grid_m'])]:
            result=checked_case(configuration(point['slip_fraction'],best['parameters']['friction_angle_deg'],best['parameters']['janosi_m'],dt=dt,grid=grid),output/f'{kind}-refinement-{source_index:02d}')
            result.update(kind=kind,source_index=source_index,traction_change_deg=result['mean_traction_slope_deg']-base['mean_traction_slope_deg'])
            refinements.append(result)
            print(json.dumps({'stage':'refinement','kind':kind,'source_index':source_index,'traction_change_deg':result['traction_change_deg']}),flush=True)
    if digest(output/'frozen-selection.json')!=frozen_hash:
        raise ValueError('Frozen selection changed after holdout evaluation')
    for file,sha256 in pinned_inputs.items():
        if digest(file)!=sha256:
            raise ValueError('Campaign input changed during execution: '+file)
    score=metrics(holdout)
    checks=p['checks']
    holdout_passed=score['controls_passed'] and score['rmse_deg']<=checks['holdout_traction_rmse_target_deg'] and score['maximum_abs_error_deg']<=checks['holdout_maximum_abs_traction_error_target_deg']
    numerical_passed=all(row['controls_passed'] and abs(row['traction_change_deg'])<=checks['maximum_'+row['kind']+'_refinement_traction_change_deg'] for row in refinements)
    report={'id':p['id'],'status':'development_targets_met' if holdout_passed and numerical_passed else 'development_targets_not_met','started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':digest(PROTOCOL),'runtime_identity':runtime['runtime_identity'],'source_reference_sha256':p['source_reference_sha256'],'frozen_selection':selection,'frozen_selection_sha256':frozen_hash,'candidates':candidates,'holdout':holdout,'holdout_metrics':score,'refinements':refinements,'holdout_targets_met':holdout_passed,'numerical_targets_met':numerical_passed,'lunar_validation_established':False,'limitations':p['limitations']}
    save(output/'campaign.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    report=campaign(parser.parse_args().output)
    print(json.dumps({'status':report['status'],'holdout_metrics':report.get('holdout_metrics'),'lunar_validation_established':False}),flush=True)
