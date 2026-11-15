"""Execute the pinned TREC discrepancy benchmark using native MuJoCo."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import mujoco
import numpy as np

from planner.validation.mobility import POLICY, comparison, simulate
from scripts.prepare_mobility_reference import ROOT, sha


def run(output):
    manifest = json.loads((ROOT / 'public/data/mobility-reference-manifest.json').read_text())
    source = ROOT / 'public/data/mobility-reference.json'
    if sha(source) != manifest['derivative']['sha256']:
        raise ValueError('Published mobility reference differs')
    reference = json.loads(source.read_text())
    out = output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, out / 'mobility-reference.json')
    shutil.copyfile(ROOT / 'public/data/mobility-reference-manifest.json', out / 'source-manifest.json')
    for file in [ROOT / 'planner/validation/mobility.py', ROOT / 'scripts/benchmark_mobility_reference.py']:
        shutil.copyfile(file, out / file.name)
    (out / 'protocol.json').write_text(json.dumps(POLICY, indent=2)+'\n')
    points = next(series['points'] for series in reference['series'] if series['id'] == 'trec-grc3-vv')
    rows, refinements = [], []
    for point in points:
        result, trace, xml = simulate(reference['rig'], point['slip_fraction'])
        result.update(source_index=point['source_index'], published_traction_slope_deg=point['traction_slope_deg'])
        rows.append(result)
        index = point['source_index']
        np.savez_compressed(out / f'point-{index:02d}.npz', trace=trace)
        (out / f'point-{index:02d}.xml').write_text(xml)
        if index in POLICY['refinement_source_indices']:
            refined, refined_trace, _ = simulate(reference['rig'], point['slip_fraction'], dt=POLICY['refined_timestep_s'])
            refined.update(source_index=index, mean_traction_difference_deg=refined['mean_traction_slope_deg']-result['mean_traction_slope_deg'])
            refinements.append(refined)
            np.savez_compressed(out / f'point-{index:02d}-refined.npz', trace=refined_trace)
        checkpoint = {'policy': POLICY, 'completed_points': rows, 'refinements': refinements}
        (out / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2, allow_nan=False)+'\n')
        print(json.dumps({'point': index, 'controls_passed': result['controls_passed'], 'published_deg': point['traction_slope_deg'], 'predicted_deg': result['mean_traction_slope_deg']}), flush=True)
    summary = comparison(rows)
    summary['refinement_targets_met'] = all(abs(row['mean_traction_difference_deg']) <= POLICY['refinement_mean_traction_target_deg'] and row['controls_passed'] for row in refinements)
    record = {'id': POLICY['id'], 'executed_utc': datetime.now(timezone.utc).isoformat(), 'engine': {'name': 'MuJoCo', 'version': mujoco.__version__, 'contact': 'Rigid Coulomb contact; no deformable soil'}, 'policy': POLICY, 'source_reference_sha256': sha(source), 'rig': reference['rig'], 'summary': summary, 'points': rows, 'refinements': refinements, 'limits': ['This independent rigid fixture uses published wheel dimensions, grousers, normal load and commanded velocities; uniform-cylinder wheel inertia and guide implementation are declared approximations.', 'NASA measurements are on GRC-3 deformable simulant under Earth gravity. The benchmark contact is a rigid plane with friction 0.7; differences diagnose model inadequacy, not measurement error.', 'Experimental points are author-distributed plotting coordinates, with no raw telemetry or reported per-point uncertainties.', 'No fitting was performed. No lunar soil calibration, VIPER flight dynamics or battery accuracy is established.'], 'evidence_files': [{'file': str(file.relative_to(out)), 'sha256': sha(file)} for file in sorted(out.iterdir()) if file.is_file()]}
    (out / 'comparison.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print(json.dumps(summary), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
