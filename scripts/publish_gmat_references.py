"""Publish a compact, hash-linked summary of executed native reference evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from planner.orbital.cases import CASES
from planner.orbital.runtime import ROOT, digest


def publish(directory):
    directory = directory.resolve()
    report = json.loads((directory / 'benchmark.json').read_text())
    if not report['passed'] or {case['case'] for case in report['cases']} != set(CASES) or report['failures']:
        raise ValueError('Only a complete passed reference benchmark can be published')
    archive = directory.with_suffix('.zip')
    with zipfile.ZipFile(archive) as bundle:
        if bundle.read('benchmark.json') != (directory / 'benchmark.json').read_bytes():
            raise ValueError('Archived benchmark differs')
        for item in report['evidence_files']:
            file = directory / item['file']
            if not file.resolve().is_relative_to(directory) or digest(file) != item['sha256'] or hashlib.sha256(bundle.read(item['file'])).hexdigest() != item['sha256']:
                raise ValueError('Evidence differs: ' + item['file'])
    cases = []
    for case in report['cases']:
        cases.append({key: case[key] for key in ['case', 'reference_checks_passed', 'screening_candidate_accepted', 'source', 'runtime_identity', 'states', 'endpoint_checks', 'initialization', 'limitations']})
        cases[-1]['native'] = {key: case['native'][key] for key in ['version', 'distribution_sha256', 'python', 'machine', 'initial_spacecraft', 'frames', 'bodies', 'burns', 'solver']}
        cases[-1]['console_api_goals_agree'] = case['console_api_goals_agree']
        cases[-1]['solver_loops'] = [{'iterations': len(loop['iterations']), 'converged': loop['converged'], 'final_goals': loop['iterations'][-1]['goals'], 'final_variables': loop['iterations'][-1]['variables']} for loop in case['solver_evidence']['console']['loops']]
    summary = {key: report[key] for key in ['model_id', 'created_utc', 'runtime_identity', 'distribution', 'native_ephemeris', 'native_build', 'passed']}
    summary.update(cases=cases, scope='Executed original NASA reference cases. No accepted bounded-search candidate, continuous clearance guarantee, launch/propellant compatibility or descent is established.', evidence={'directory': str(directory.relative_to(ROOT)), 'benchmark_sha256': digest(directory / 'benchmark.json'), 'archive': str(archive.relative_to(ROOT)), 'archive_sha256': digest(archive), 'archive_bytes': archive.stat().st_size, 'report': 'docs/GMAT_REFERENCES.md'})
    target = ROOT / 'public/data/gmat-reference-validation.json'
    target.write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    validation = ROOT / 'docs/validation/gmat-reference-benchmark.json'
    validation.write_bytes(target.read_bytes())
    file_record = {'url': '/data/gmat-reference-validation.json', 'sha256': digest(target), 'bytes': target.stat().st_size, 'model_id': summary['model_id'], 'status': 'Both original reference cases passed. Bounded departure search and full clearance/repropagation gates remain pending.'}
    manifest_file = ROOT / 'public/data/manifest.json'
    manifest = json.loads(manifest_file.read_text())
    manifest['orbital_references'] = {'software': 'NASA GMAT R2026a, official signed universal macOS distribution', 'role': 'Offline reference benchmark, separate from the surface/dynamics models', 'native_ephemeris': 'DE405', 'native_lunar_radius_m': 1738200, 'distribution_sha256': summary['distribution']['sha256'], 'runtime_identity': summary['runtime_identity'], 'source_manifest': 'planner/orbital/references/manifest.json', 'report': file_record}
    manifest_file.write_text(json.dumps(manifest, indent=2) + '\n')
    source_file = ROOT / 'planner/orbital/references/manifest.json'
    source_manifest = json.loads(source_file.read_text())
    source_manifest['execution_record'] = {'report': 'docs/GMAT_REFERENCES.md', 'summary': 'public/data/gmat-reference-validation.json', 'summary_sha256': digest(target), 'benchmark_sha256': summary['evidence']['benchmark_sha256'], 'archive_sha256': summary['evidence']['archive_sha256'], 'reference_checks_passed': True, 'screening_candidates_accepted': False}
    source_file.write_text(json.dumps(source_manifest, indent=2) + '\n')
    print(json.dumps(file_record))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    publish(parser.parse_args().directory)
