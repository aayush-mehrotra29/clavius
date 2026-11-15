"""Publish complete mobility evidence, including failed physical/numerical gates."""
import argparse
import json
from pathlib import Path
import zipfile

from scripts.prepare_mobility_reference import ROOT, sha


def publish(directory):
    directory = directory.resolve()
    record = json.loads((directory / 'comparison.json').read_text())
    reference = json.loads((directory / 'mobility-reference.json').read_text())
    expected = next(series for series in reference['series'] if series['id'] == 'trec-grc3-vv')['points']
    if [point['source_index'] for point in record['points']] != [point['source_index'] for point in expected] or len(record['points']) != 18:
        raise ValueError('Incomplete point comparison')
    for item in record['evidence_files']:
        file = directory / item['file']
        if not file.resolve().is_relative_to(directory) or sha(file) != item['sha256']:
            raise ValueError('Evidence differs: ' + item['file'])
    if sha(ROOT / 'public/data/mobility-reference.json') != record['source_reference_sha256']:
        raise ValueError('Public source reference differs from executed input')
    archive = directory.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(directory.iterdir()):
            if file.is_file():
                bundle.write(file, file.name)
    figure = ROOT / 'public/data/mobility-validation.png'
    snapshot = {key: record[key] for key in ['id', 'executed_utc', 'engine', 'policy', 'source_reference_sha256', 'rig', 'summary', 'points', 'refinements', 'limits']}
    snapshot.update(source_page=reference['paper']['ntrs_record'], source_manifest='/data/mobility-reference-manifest.json', observed_points='/data/mobility-reference.json', report='docs/MOBILITY_VALIDATION.md', figure={'url': '/data/mobility-validation.png', 'sha256': sha(figure), 'bytes': figure.stat().st_size}, evidence={'directory': str(directory.relative_to(ROOT)), 'comparison_sha256': sha(directory / 'comparison.json'), 'archive': str(archive.relative_to(ROOT)), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size})
    target = ROOT / 'public/data/mobility-validation.json'
    target.write_text(json.dumps(snapshot, indent=2, allow_nan=False)+'\n')
    (ROOT / 'docs/validation/mobility-reference-comparison.json').write_bytes(target.read_bytes())
    shared = {'role': 'validation_only', 'source': 'NASA Glenn TREC / MGRU3 published experimental plot points and author rig definitions', 'source_manifest': '/data/mobility-reference-manifest.json', 'report': {'url': '/data/mobility-validation.json', 'sha256': sha(target), 'bytes': target.stat().st_size, 'model_id': snapshot['id']}, 'status': 'Independent rigid-contact discrepancy test; no lunar soil calibration established', 'terrain_role': 'No new lunar terrain, regolith map or mission mobility response added.'}
    for path in [ROOT / 'public/data/manifest.json', ROOT / 'public/data/simulation-manifest.json']:
        manifest = json.loads(path.read_text())
        manifest['mobility_validation'] = shared
        path.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(shared['report']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    publish(parser.parse_args().directory)
