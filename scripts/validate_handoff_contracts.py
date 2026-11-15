"""Validate handoff fixtures and cross-message scientific interface conventions.

Run: uv run --with 'jsonschema[format]' python scripts/validate_handoff_contracts.py
This does not execute GMAT, calculate ephemerides, or validate lunar physics.
"""
from pathlib import Path
from datetime import datetime
from copy import deepcopy
import hashlib
import json
import math

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'contracts/v0.1'
EXAMPLES = ROOT / 'examples/integration'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def invalid_constant(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    return json.loads(path.read_text(), parse_constant=invalid_constant)


def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'Non-finite number')
    elif isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def unit(vector):
    require(abs(sum(x*x for x in vector) - 1) < 1e-9, 'Expected a unit vector/quaternion')


def ordered(samples):
    times = [sample['t_s'] for sample in samples]
    require(all(b > a for a, b in zip(times, times[1:])), 'Times must strictly increase')


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def verify_assets(value):
    if isinstance(value, dict):
        if set(value) == {'uri', 'sha256'}:
            path = (EXAMPLES / value['uri']).resolve()
            require(path.is_relative_to(EXAMPLES.resolve()), 'Fixture asset escapes bundle')
            require(path.is_file(), f'Missing fixture asset: {path}')
            require(hashlib.sha256(path.read_bytes()).hexdigest() == value['sha256'],
                    f'Asset hash mismatch: {path.name}')
        for child in value.values():
            verify_assets(child)
    elif isinstance(value, list):
        for child in value:
            verify_assets(child)


def robot_checks(robot):
    p = robot['power']
    require(p['reserve_wh'] <= p['battery_capacity_wh'], 'Reserve exceeds nominal capacity')
    require(all(x > 0 for x in robot['dimensions_m']), 'Robot dimensions must be positive')
    unit(p['array_normal_body_unit'])
    domain = robot['mobility']['validity_domain']
    require(domain['slope_min_deg'] <= domain['slope_max_deg'], 'Invalid slope domain')
    require(domain['speed_min_m_s'] <= domain['speed_max_m_s'], 'Invalid speed domain')


def transfer_checks(candidate):
    if candidate['candidate_status'] == 'accepted_for_screening':
        require(candidate['solver_status'] == 'converged', 'Accepted candidate has not converged')
        require(candidate['verification_status'] == 'passed', 'Accepted candidate is unverified')
        for field in ['departure_utc', 'encounter_utc', 'capture_utc', 'departure_state',
                      'capture_state', 'script_sha256', 'total_maneuver_delta_v_m_s',
                      'minimum_lunar_clearance_m', 'capture_eccentricity']:
            require(candidate[field] is not None, f'Accepted candidate missing {field}')
        require(dt(candidate['departure_utc']) < dt(candidate['encounter_utc']) <= dt(candidate['capture_utc']),
                'Invalid departure/encounter/capture order')
        require(candidate['minimum_lunar_clearance_m'] > 0, 'Nonpositive lunar clearance')
        require(0 <= candidate['capture_eccentricity'] < 1, 'Capture is not an elliptic orbit')
        require(candidate['target_residuals'], 'Accepted candidate has no residuals')
        require(all(abs(r['residual']) <= r['tolerance'] for r in candidate['target_residuals']),
                'Candidate residual exceeds tolerance')
        require(candidate['departure_state']['central_body'] == 'EARTH', 'Departure origin mismatch')
        require(candidate['capture_state']['central_body'] == 'MOON', 'Capture origin mismatch')
        require(candidate['departure_state']['epoch_utc'] == candidate['departure_utc'],
                'Departure state epoch mismatch')
        require(candidate['capture_state']['epoch_utc'] == candidate['capture_utc'],
                'Capture state epoch mismatch')
        require(candidate['maneuvers'], 'Accepted candidate has no maneuvers')
        total = sum(math.sqrt(sum(x*x for x in m['delta_v_m_s'])) for m in candidate['maneuvers'])
        require(math.isclose(total, candidate['total_maneuver_delta_v_m_s'], rel_tol=1e-8, abs_tol=1e-8),
                'Maneuver delta-v total mismatch')


def main():
    schemas = {p.name: read_json(p) for p in SCHEMAS.glob('*.schema.json')}
    for item in schemas.values():
        Draft202012Validator.check_schema(item)
    registry = Registry().with_resources([
        (s['$id'], Resource.from_contents(s)) for s in schemas.values()])
    messages = {}
    for path in sorted(EXAMPLES.glob('*.json')):
        value = read_json(path)
        validator = Draft202012Validator(schemas[path.stem + '.schema.json'],
                                        registry=registry, format_checker=FormatChecker())
        validator.validate(value)
        finite(value)
        verify_assets(value)
        messages[path.stem] = value

    robot = messages['robot-capability']
    environment = messages['environment-package']
    request = messages['planning-request']
    evaluation = messages['plan-evaluation']
    response = messages['vehicle-response']
    segment = messages['vehicle-segment-request']
    candidate = messages['transfer-candidate']
    robot_checks(robot)
    ordered(environment['sky_samples'])
    rotation = environment['origin']['enu_to_body_fixed_rotation']
    columns = list(zip(*rotation))
    for col in columns:
        unit(col)
    for i, a in enumerate(columns):
        for b in columns[i+1:]:
            require(abs(sum(x*y for x, y in zip(a, b))) < 1e-9, 'Frame matrix not orthogonal')
    east, north, up = columns
    cross = [east[1]*north[2]-east[2]*north[1], east[2]*north[0]-east[0]*north[2],
             east[0]*north[1]-east[1]*north[0]]
    require(sum(a*b for a, b in zip(cross, up)) > 0.999999, 'Frame is not right handed')
    for sample in environment['sky_samples']:
        unit(sample['sun_direction_enu_unit'])
        unit(sample['earth_direction_enu_unit'])
    for key in ['robot_ref', 'environment_ref']:
        require(request[key] == evaluation[key] == segment[key] == response[key],
                f'Immutable reference mismatch: {key}')
    require(evaluation['request_id'] == request['request_id'] == candidate['request_id'],
            'Request identity mismatch')
    require(request['surface']['site_id'] == environment['site_id'], 'Site mismatch')
    require(request['surface']['touchdown_utc'] == environment['time_origin_utc'], 'Time origin mismatch')
    require(environment['sky_samples'][0]['t_s'] == 0, 'Environment must cover start')
    require(environment['sky_samples'][-1]['t_s'] >= request['surface']['duration_s'],
            'Environment does not cover the mission')
    departure = request['departure_screening']
    require(dt(departure['departure_start_utc']) <= dt(departure['departure_end_utc']),
            'Departure interval is reversed')
    delay = departure['capture_to_touchdown']
    require(delay['min_s'] <= delay['max_s'], 'Capture-to-touchdown interval is reversed')
    surface = evaluation['surface_result']
    ordered(surface['samples'])
    require(surface['samples'][0]['t_s'] == 0 and
            surface['samples'][-1]['t_s'] == request['surface']['duration_s'], 'Timeline span mismatch')
    energies = [s['battery_energy_wh'] for s in surface['samples']]
    require(math.isclose(min(energies), surface['minimum_battery_wh']), 'Battery minimum mismatch')
    require(math.isclose(surface['minimum_battery_wh'] - robot['power']['reserve_wh'],
                         surface['battery_reserve_margin_wh']), 'Reserve margin mismatch')
    require(max(energies) <= robot['power']['battery_capacity_wh'], 'Battery exceeds capacity')
    if surface['status'] == 'supported_under_assumptions':
        required = {t['task_id'] for t in request['surface']['required_tasks']}
        require(required <= set(surface['required_tasks_completed']), 'Required task missing')
        require(surface['first_violation'] is None, 'Supported fixture reports a violation')
    # The power fixture uses left-constant loads, no capacity clipping, and exact hour intervals.
    for a, b in zip(surface['samples'], surface['samples'][1:]):
        net = a['solar_power_w'] - a['total_load_w']
        delta_w = net * robot['power']['charge_efficiency'] if net >= 0 else net / robot['power']['discharge_efficiency']
        expected = a['battery_energy_wh'] + delta_w * (b['t_s'] - a['t_s']) / 3600
        require(math.isclose(expected, b['battery_energy_wh'], abs_tol=1e-8), 'Energy fixture accounting mismatch')
    require(response['segment_id'] == segment['segment_id'], 'Segment identity mismatch')
    require(response['time_origin_utc'] == segment['time_origin_utc'] == environment['time_origin_utc'],
            'Segment clock mismatch')
    require(response['power_basis'] == robot['mobility']['power_basis'], 'Power convention mismatch')
    ordered(response['samples'])
    require(response['samples'][0]['t_s'] == segment['start_t_s'] and
            response['samples'][-1]['t_s'] == segment['start_t_s'] + segment['duration_s'],
            'Segment duration mismatch')
    require(segment['start_t_s'] + segment['duration_s'] <= environment['sky_samples'][-1]['t_s'],
            'Environment does not cover segment')
    controls = segment['controls']
    require(controls[0]['start_t_s'] == segment['start_t_s'], 'Control start mismatch')
    for a, b in zip(controls, controls[1:]):
        require(math.isclose(a['start_t_s'] + a['duration_s'], b['start_t_s']),
                'Controls have gaps or overlaps')
    require(math.isclose(controls[-1]['start_t_s'] + controls[-1]['duration_s'],
                         segment['start_t_s'] + segment['duration_s']), 'Control end mismatch')
    unit(segment['initial_state']['orientation_body_to_enu_xyzw'])
    for sample in response['samples']:
        unit(sample['orientation_body_to_enu_xyzw'])
    energy = sum(a['mobility_bus_power_w'] * (b['t_s']-a['t_s']) / 3600
                 for a, b in zip(response['samples'], response['samples'][1:]))
    require(math.isclose(energy, response['mobility_bus_energy_wh']), 'Mobility energy mismatch')
    transfer_checks(candidate)

    # Ensure semantic checks reject representative integration mistakes.
    negative_cases = 0
    bad = deepcopy(robot)
    bad['power']['reserve_wh'] = 2000
    try:
        robot_checks(bad)
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject impossible nominal reserve')
    bad = deepcopy(candidate)
    bad['candidate_status'] = 'accepted_for_screening'
    try:
        transfer_checks(bad)
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject fabricated accepted transfer')
    try:
        ordered([{'t_s': 1}, {'t_s': 1}])
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject duplicate timestamps')
    try:
        unit([1, 1, 0])
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject a non-unit vector')

    print(f'PASS: {len(schemas)} schemas; {len(messages)} messages; hashes, frames, clocks, power and statuses checked.')
    print(f'PASS: {negative_cases} deliberately invalid cases rejected.')
    print('Scope: interface and analytical fixtures only; GMAT, ephemeris and lunar physics are not executed.')


if __name__ == '__main__':
    main()
