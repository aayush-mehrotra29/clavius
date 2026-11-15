"""Extract published experimental plot points without executing research scripts.

Inputs are pinned author sources for NASA Glenn TREC / MGRU3 tests. These are
the numeric points distributed with a paper, not raw rig telemetry. The PDF and
full source remain in the local research cache; only factual derivatives publish.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/robots/crm_sim_nasa_exp_scripts'
COMMIT = '54f74dc514b394d3a02e15d7508b1bf27a88d1a6'
REPOSITORY = 'https://github.com/sjtumsd/crm_sim_nasa_exp_scripts'
PAPER = 'https://ntrs.nasa.gov/api/citations/20250001809/downloads/main-20250215.pdf'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def literal_arrays(text):
    arrays = {}
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in ['experimental1', 'experimental2', 'experimental3']:
            continue
        if name in arrays or not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Attribute) or not isinstance(node.value.func.value, ast.Name) or node.value.func.value.id != 'numpy' or node.value.func.attr != 'array' or len(node.value.args) != 1 or node.value.keywords:
            raise ValueError('Unexpected experimental array expression')
        values = ast.literal_eval(node.value.args[0])
        if not isinstance(values, list) or len(values) % 2 or not values or not all(type(value) in [int, float] and math.isfinite(value) for value in values):
            raise ValueError('Invalid finite paired experimental array')
        arrays[name] = [values[i:i+2] for i in range(0, len(values), 2)]
    if set(arrays) != {'experimental1', 'experimental2', 'experimental3'}:
        raise ValueError('Missing experimental arrays')
    return arrays


def prepare():
    import subprocess
    if subprocess.check_output(['git', '-C', str(RAW), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise ValueError('Research source checkout differs from the pinned commit')
    plot = RAW / 'images/figure4b.py'
    demo = RAW / 'demos/single_wheel_vv_mode/demo_FSI_SingleWheelTest_VV_mode.cpp'
    arrays = literal_arrays(plot.read_text())
    # Verify against original committed bytes, not just the checkout's HEAD name.
    for file in [plot, demo, RAW / 'README.md']:
        original = subprocess.check_output(['git', '-C', str(RAW), 'show', COMMIT+':'+str(file.relative_to(RAW))])
        if original != file.read_bytes():
            raise ValueError('Modified research input: ' + file.name)
    text = demo.read_text()
    parameters = {}
    for name in ['wheel_radius', 'wheel_wide', 'grouser_height', 'grouser_wide', 'grouser_num', 'wheel_vel', 'total_mass']:
        matches = re.findall(r'^(?:double|int) '+name+r'\s*=\s*([\d.]+);', text, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('Missing source rig parameter ' + name)
        parameters[name] = float(matches[0])
    series = []
    for name, identity, label, soil in [
        ('experimental1', 'trec-grc3-vv', 'TREC nominal tests, GRC-3', 'GRC-3'),
        ('experimental2', 'mgru3-grc1-2021', 'MGRU3 SLOPE lab tests, 2021', 'GRC-1'),
        ('experimental3', 'mgru3-grc1-2022', 'MGRU3 SLOPE lab tests, 2022', 'GRC-1')]:
        series.append({'id': identity, 'label': label, 'source_array': name, 'soil': soil, 'gravity_m_s2': 9.81, 'mode': 'controlled_translation_and_rotation' if name == 'experimental1' else 'free_translation_fixed_wheel_speed_on_slope', 'points': [{'source_index': index, 'slip_fraction': slip/100, 'traction_slope_deg' if name == 'experimental1' else 'terrain_slope_deg': slope} for index, (slip, slope) in enumerate(arrays[name])], 'limits': 'Published author plotting coordinates. Replicates, small negative values and full numeric precision retained. Raw telemetry, sample counts, error bars and exact soil preparation for each point are not supplied here.'})
    paper = ROOT / 'data/raw/robots/research/mobility-gravity-2025.pdf'
    files = [{'role': role, 'url': url, 'local_file': str(file.relative_to(ROOT)), 'sha256': sha(file), 'bytes': file.stat().st_size} for role, url, file in [
        ('NASA-hosted paper preprint; 15 February 2025 PDF', PAPER, paper),
        ('Author experimental plot-point arrays', REPOSITORY+'/blob/'+COMMIT+'/images/figure4b.py', plot),
        ('Author single-wheel rig definition', REPOSITORY+'/blob/'+COMMIT+'/demos/single_wheel_vv_mode/demo_FSI_SingleWheelTest_VV_mode.cpp', demo),
        ('Author reproduction requirements', REPOSITORY+'/blob/'+COMMIT+'/README.md', RAW/'README.md')]]
    record = {'id': 'nasa-glenn-published-mobility-reference-v1', 'prepared_utc': datetime.now(timezone.utc).isoformat(), 'role': 'validation_only', 'paper': {'title': 'A study demonstrating that using gravitational offset to prepare extraterrestrial mobility missions is misleading', 'ntrs_record': 'https://ntrs.nasa.gov/citations/20250001809', 'publication_date': '2025-03-31', 'downloaded_version': '2025-02-15 preprint', 'relevant_pages': [3, 4, 10, 11, 12, 13, 21]}, 'author_code': {'repository': REPOSITORY, 'commit': COMMIT, 'license_scope': 'Chrono declares BSD-3-Clause; the supplementary scripts repository has no top-level license. Original research scripts are not redistributed by this derivative.'}, 'sources': files, 'rig': {'wheel_outer_radius_m': parameters['wheel_radius'], 'wheel_width_m': parameters['wheel_wide'], 'grouser_height_m': parameters['grouser_height'], 'grouser_tangential_width_m': parameters['grouser_wide'], 'grouser_count': int(parameters['grouser_num']), 'normal_loaded_mass_kg': parameters['total_mass'], 'translation_m_s': parameters['wheel_vel'], 'slip_definition': 's = 1 - v / (omega * outer_radius), positive driving direction', 'support': 'Wheel plus vertically free axle each carry half the normal-loaded mass. Horizontal carriage weight is supported by its guide.'}, 'series': series, 'lunar_transfer_of_calibration': 'Not established. Earth simulant tests do not directly calibrate local lunar regolith, and changing vehicle gravity alone does not model soil gravity.', 'robot_scope': 'TREC is a single-wheel laboratory rig. MGRU3 is a reduced-mass VIPER prototype, not final flight hardware. No VIPER battery/thermal/actuator certification is supplied.'}
    target = ROOT / 'public/data/mobility-reference.json'
    target.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    manifest = {'id': record['id'], 'role': record['role'], 'sources': files, 'derivative': {'url': '/data/mobility-reference.json', 'sha256': sha(target), 'bytes': target.stat().st_size, 'script': 'scripts/prepare_mobility_reference.py'}, 'limits': record['lunar_transfer_of_calibration']}
    (ROOT / 'public/data/mobility-reference-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest['derivative']))


if __name__ == '__main__':
    prepare()
