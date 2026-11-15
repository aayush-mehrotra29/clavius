"""Verify and publish a completed frozen-split native SCM development campaign."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import zipfile

import numpy as np

from planner.validation.scm import ROOT,PROTOCOL,configuration,digest,protocol,summarize
from scripts.benchmark_scm_reference import metrics


def checked_campaign(directory):
    directory=Path(directory).resolve()
    report=json.loads((directory/'campaign.json').read_text())
    p,points=protocol()
    if digest(directory/'protocol.json')!=digest(PROTOCOL) or report['protocol_sha256']!=digest(PROTOCOL):
        raise ValueError('Executed SCM protocol differs')
    if digest(ROOT/'planner/validation/scm.py')!=digest(directory/'scm.py'):
        raise ValueError('Current scoring code differs from the executed snapshot')
    if digest(directory/'published-reference.json')!=p['source_reference_sha256'] or digest(ROOT/'public/data/mobility-reference.json')!=p['source_reference_sha256']:
        raise ValueError('Executed source points differ')
    if report['status'] not in ['development_targets_met','development_targets_not_met'] or report['lunar_validation_established']:
        raise ValueError('Incomplete campaign or unsupported validation claim')
    frozen=directory/'frozen-selection.json'
    if digest(frozen)!=report['frozen_selection_sha256'] or json.loads(frozen.read_text())!=report['frozen_selection']:
        raise ValueError('Frozen selection differs')
    selection=report['frozen_selection']
    runtime=json.loads((directory/'runtime.json').read_text())
    if selection['runtime_identity']!=runtime['runtime_identity'] or report['runtime_identity']!=runtime['runtime_identity']:
        raise ValueError('Campaign mixes runtime identities')
    if selection['holdout_results_seen'] is not False:
        raise ValueError('Selection was not frozen before holdout')
    candidates=report['candidates']
    allowed=list(itertools.product(p['calibration_variables']['friction_angle_deg'],p['calibration_variables']['janosi_m']))
    if len(candidates)!=len(allowed) or len(candidates)!=p['maximum_parameter_candidates']:
        raise ValueError('Incomplete parameter campaign')
    frozen_time=datetime.fromisoformat(selection['frozen_utc'])

    def check_case(row,relative,phi,janosi,*,stage,dt=None,grid=None):
        case=directory/relative
        index=row['source_index'];point=points[index]
        expected=configuration(point['slip_fraction'],phi,janosi,dt=dt,grid=grid)
        invocation=json.loads((case/'invocation.json').read_text())
        config=json.loads((case/'input.json').read_text())
        stored=json.loads((case/'result.json').read_text())
        if config!=expected or row['configuration']!=expected or stored['configuration']!=expected:
            raise ValueError('Case does not match its declared conditions')
        if invocation['state']!='completed' or invocation['returncode']!=0 or invocation['runtime_identity']!=runtime['runtime_identity']:
            raise ValueError('Uncompleted or changed native execution')
        if invocation['protocol_sha256']!=report['protocol_sha256'] or invocation['input_sha256']!=digest(case/'input.json'):
            raise ValueError('Invocation inputs differ')
        if any(value['runtime_identity']!=runtime['runtime_identity'] or value['input_sha256']!=invocation['input_sha256'] for value in [row,stored]):
            raise ValueError('Result input/runtime identity differs')
        if stage!='training' and datetime.fromisoformat(invocation['started_utc'])<frozen_time:
            raise ValueError('Holdout or refinement executed before selection freeze')
        if stored['trace_sha256']!=digest(case/'trace.csv') or row['trace_sha256']!=stored['trace_sha256']:
            raise ValueError('Native trace differs')
        actual=summarize(np.genfromtxt(case/'trace.csv',delimiter=',',names=True),config)
        for key,value in actual.items():
            if row[key]!=value or stored[key]!=value:
                raise ValueError('Scored telemetry differs: '+key)
        if stage!='refinement' and row['published_traction_slope_deg']!=point['traction_slope_deg']:
            raise ValueError('Published observation changed')
        if row['lunar_validation_established']:
            raise ValueError('Earth test cannot establish lunar validation')

    for index,(candidate,parameters) in enumerate(zip(candidates,allowed,strict=True)):
        phi,janosi=parameters
        if candidate['index']!=index or candidate['parameters']!={'friction_angle_deg':phi,'janosi_m':janosi}:
            raise ValueError('Candidate list differs from the frozen protocol')
        if [row['source_index'] for row in candidate['training']]!=p['training_source_indices']:
            raise ValueError('Training split differs')
        for row in candidate['training']:
            check_case(row,f"candidate-{index}/training-{row['source_index']:02d}",phi,janosi,stage='training')
        if metrics(candidate['training'])!=candidate['training_metrics']:
            raise ValueError('Training metrics differ')
    training_hash=hashlib.sha256(json.dumps(candidates,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if training_hash!=selection['training_evidence_sha256']:
        raise ValueError('Frozen training evidence differs')
    eligible=[candidate for candidate in candidates if candidate['training_metrics']['controls_passed']]
    best=min(eligible,key=lambda candidate:(candidate['training_metrics']['rmse_deg'],candidate['index']))
    if selection['selected_index']!=best['index'] or selection['parameters']!=best['parameters']:
        raise ValueError('Selection was not determined by training metrics alone')
    if [row['source_index'] for row in report['holdout']]!=p['holdout_source_indices']:
        raise ValueError('Holdout split differs')
    phi=best['parameters']['friction_angle_deg'];janosi=best['parameters']['janosi_m']
    for row in report['holdout']:
        check_case(row,f"holdout-{row['source_index']:02d}",phi,janosi,stage='holdout')
    expected_refinements=[(index,kind) for index in p['numerical_refinement_source_indices'] for kind in ['time','grid']]
    if [(row['source_index'],row['kind']) for row in report['refinements']]!=expected_refinements:
        raise ValueError('Incomplete numerical refinements')
    for row in report['refinements']:
        kind=row['kind'];index=row['source_index']
        check_case(row,f'{kind}-refinement-{index:02d}',phi,janosi,stage='refinement',dt=p['refined_dt_s'] if kind=='time' else p['base_dt_s'],grid=p['refined_grid_m'] if kind=='grid' else p['base_grid_m'])
        base=next(base for base in best['training']+report['holdout'] if base['source_index']==index)
        if row['traction_change_deg']!=row['mean_traction_slope_deg']-base['mean_traction_slope_deg']:
            raise ValueError('Refinement difference changed')
    score=metrics(report['holdout']);checks=p['checks']
    physical=score['controls_passed'] and score['rmse_deg']<=checks['holdout_traction_rmse_target_deg'] and score['maximum_abs_error_deg']<=checks['holdout_maximum_abs_traction_error_target_deg']
    numerical=all(row['controls_passed'] and abs(row['traction_change_deg'])<=checks['maximum_'+row['kind']+'_refinement_traction_change_deg'] for row in report['refinements'])
    if score!=report['holdout_metrics'] or physical!=report['holdout_targets_met'] or numerical!=report['numerical_targets_met']:
        raise ValueError('Campaign acceptance metrics differ')
    return report,p,best


def publish(directory):
    directory=Path(directory).resolve()
    report,p,best=checked_campaign(directory)
    rigid_file=ROOT/'public/data/mobility-validation.json'
    rigid=json.loads(rigid_file.read_text())
    if rigid['source_reference_sha256']!=p['source_reference_sha256']:
        raise ValueError('Rigid baseline uses another source')
    holdout_indices=p['holdout_source_indices']
    baseline=metrics([row for row in rigid['points'] if row['source_index'] in holdout_indices])
    files=[{'file':str(file.relative_to(directory)),'sha256':digest(file),'bytes':file.stat().st_size} for file in sorted(directory.rglob('*')) if file.is_file() and file.name!='evidence-index.json']
    (directory/'evidence-index.json').write_text(json.dumps(files,indent=2)+'\n')
    archive=directory.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(directory.rglob('*')):
            if file.is_file():bundle.write(file,file.relative_to(directory))
    figure=ROOT/'public/data/scm-validation.png'
    snapshot={key:report[key] for key in ['id','status','started_utc','finished_utc','protocol_sha256','runtime_identity','source_reference_sha256','frozen_selection','frozen_selection_sha256','holdout','holdout_metrics','refinements','holdout_targets_met','numerical_targets_met','lunar_validation_established','limitations']}
    case_count=sum(len(candidate['training']) for candidate in report['candidates'])+len(report['holdout'])+len(report['refinements'])
    snapshot.update(engine={'name':'Project Chrono CPU SCM','version':'9.0.1','upstream_commit':p['upstream_commit'],'source':'https://github.com/projectchrono/chrono'},protocol=p,training=best['training'],candidate_training_scores=[{'index':candidate['index'],'parameters':candidate['parameters'],'metrics':candidate['training_metrics']} for candidate in report['candidates']],matched_rigid_baseline={'source_url':'/data/mobility-validation.json','source_sha256':digest(rigid_file),'source_indices':holdout_indices,'metrics':baseline,'role':'Same eight held-out plotting coordinates; rigid parameters were not fitted.'},figure={'url':'/data/scm-validation.png','sha256':digest(figure),'bytes':figure.stat().st_size},evidence={'directory':str(directory.relative_to(ROOT)),'campaign_sha256':digest(directory/'campaign.json'),'archive':str(archive.relative_to(ROOT)),'archive_sha256':digest(archive),'archive_bytes':archive.stat().st_size,'case_count':case_count,'evidence_index_sha256':digest(directory/'evidence-index.json')},source_page='https://ntrs.nasa.gov/citations/20250001809',active_app_dynamics=False)
    snapshot['material_interpretation']='Selected parameters are effective development inputs, not measured GRC-3 properties. The paper reports GRC-3 bulk friction-angle scenarios 37.8, 42.0 and 47.8 degrees with different densities; selecting 30 degrees here does not identify or calibrate the actual bulk friction angle.'
    target=ROOT/'public/data/scm-validation.json'
    target.write_text(json.dumps(snapshot,indent=2,allow_nan=False)+'\n')
    (ROOT/'docs/validation/scm-reference-comparison.json').write_bytes(target.read_bytes())
    shared={'role':'offline_experimental_development','source':'Same NASA Glenn TREC Earth-gravity published plot points; no new lunar measurements','source_manifest':'/data/mobility-reference-manifest.json','software':snapshot['engine'],'report':{'url':'/data/scm-validation.json','sha256':digest(target),'bytes':target.stat().st_size,'model_id':snapshot['id']},'status':snapshot['status'],'active_app_dynamics':False,'lunar_validation_established':False}
    for path in [ROOT/'public/data/manifest.json',ROOT/'public/data/simulation-manifest.json']:
        manifest=json.loads(path.read_text());manifest['scm_validation']=shared
        path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'report':shared['report'],'holdout':report['holdout_metrics'],'matched_rigid_baseline':baseline,'numerical_targets_met':report['numerical_targets_met']}),flush=True)
    return snapshot


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    publish(parser.parse_args().directory)
