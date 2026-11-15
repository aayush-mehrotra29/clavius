"""Conservative checks of native reference evidence, independent of GMAT imports.

Endpoint/osculating checks here are deliberately weaker than the full trajectory
clearance and tighter repropagation required for a screening candidate.
"""
from __future__ import annotations

from datetime import date
import math
import re


class EvidenceError(ValueError):
    """Native evidence is missing, inconsistent, or uses unsupported conventions."""


def finite(value):
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise EvidenceError('Invalid numeric evidence: ' + str(value)) from error
    if not math.isfinite(number):
        raise EvidenceError('Nonfinite native evidence')
    return number


def one(pattern, text):
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise EvidenceError('Expected exactly one native field: ' + pattern)
    return matches[0]


def solver_log(text, expected):
    """Preserve every nominal iteration; require the expected goals and markers."""
    blocks = text.split('*** Performing Differential Correction (using "DC1")')[1:]
    if len(blocks) != len(expected):
        raise EvidenceError('Missing or unexpected differential-correction loops')
    result = []
    for block, targets in zip(blocks, expected):
        iterations = []
        nominal = list(re.finditer(r'^DC1 Iteration (\d+); Nominal Pass\s*$', block, re.MULTILINE))
        for index, match in enumerate(nominal):
            section = block[match.end():nominal[index+1].start() if index+1 < len(nominal) else len(block)]
            rows = re.findall(r'^\s+(\S+)\s+Desired:\s*(\S+)\s+Achieved:\s*(\S+)\s+Variance:\s*(\S+)\s*$', section, re.MULTILINE)
            if [row[0] for row in rows] != [target[0] for target in targets]:
                raise EvidenceError('Missing, reordered, or unexpected target expression')
            goals = []
            for (name, desired, achieved, variance), (_, target, tolerance, unit) in zip(rows, targets):
                desired, achieved, variance = map(finite, [desired, achieved, variance])
                if not math.isclose(desired, target, rel_tol=1e-11, abs_tol=1e-11):
                    raise EvidenceError('Native goal differs from pinned source: ' + name)
                residual = achieved - desired
                if not math.isclose(variance, -residual, rel_tol=1e-8, abs_tol=max(1e-7, abs(desired)*1e-10, abs(achieved)*1e-10)):
                    raise EvidenceError('Inconsistent native residual: ' + name)
                goals.append(dict(name=name, desired=desired, achieved=achieved, residual=residual, native_variance=variance, tolerance=tolerance, unit=unit, passed=abs(residual) <= tolerance))
            variables = one(r'^\s*Variables:\s+(.+)$', section)
            variables = dict((name, finite(value)) for name, value in re.findall(r'([\w.]+)\s*=\s*([^,\s]+)', variables))
            iterations.append({'iteration': int(match[1]), 'goals': goals, 'variables': variables})
        if not iterations or [item['iteration'] for item in iterations] != list(range(1, len(iterations)+1)):
            raise EvidenceError('Missing or inconsistent nominal iterations')
        completed = re.findall(r'^\*\*\* Targeting Completed in (\d+) iterations\.', block, re.MULTILINE)
        converged = block.count('*** The Targeter converged!') == 1
        terminated = completed == [str(len(iterations))]
        result.append({'converged': converged, 'termination_marker_matches': terminated, 'iterations': iterations, 'passed': converged and terminated and all(goal['passed'] for goal in iterations[-1]['goals'])})
    return {'loops': result, 'mission_completed': text.count('Mission run completed.') == 1, 'passed': all(loop['passed'] for loop in result) and text.count('Mission run completed.') == 1}


def utc_iso(gregorian):
    """Retain a native leap second if present; never use UTC subtraction for SI."""
    match = re.fullmatch(r'(\d{1,2}) ([A-Z][a-z]{2}) (\d{4}) (\d{2}):(\d{2}):(\d{2}\.\d+)', gregorian)
    if not match:
        raise EvidenceError('Unsupported native UTC Gregorian format')
    day, month, year, hour, minute, second = match.groups()
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    if month not in months or int(hour) > 23 or int(minute) > 59 or not 0 <= finite(second) < 61:
        raise EvidenceError('Invalid native UTC fields')
    date(int(year), months.index(month)+1, int(day))
    return f'{year}-{months.index(month)+1:02d}-{int(day):02d}T{hour}:{minute}:{second}Z'


def summary_state(text, spacecraft, frame, origin, axes):
    if origin not in ['Earth', 'Luna'] or axes not in ['MJ2000Eq', 'BodyInertial']:
        raise EvidenceError('Only declared inertial report frames are supported')
    blocks = re.split(r'Spacecraft\s*:\s*(\S+)', text)
    # Maneuver reports repeat "Spacecraft:" in the burn metadata, which is not
    # another Cartesian state. Require the actual coordinate-system header.
    selected = [blocks[i+1] for i in range(1, len(blocks), 2) if blocks[i] == spacecraft and re.match(r'\s*Coordinate System:', blocks[i+1])]
    if len(selected) != 1:
        raise EvidenceError('Missing or duplicate intended spacecraft state')
    block = selected[0]
    if one(r'^\s*Coordinate System:\s*(\S+)\s*$', block) != frame:
        raise EvidenceError('Native report coordinate frame mismatch')
    utc, utc_mjd = one(r'^\s*UTC Epoch:\s*(.*?)\s+([\d.]+)\s*$', block)
    tai, tai_mjd = one(r'^\s*TAI Epoch:\s*(.*?)\s+([\d.]+)\s*$', block)
    position = [finite(one(r'^\s*' + axis + r'\s*=\s*(\S+)\s+km\s', block))*1000 for axis in ['X', 'Y', 'Z']]
    velocity = [finite(one(r'^\s*' + axis + r'\s*=\s*(\S+)\s+km/sec\s', block))*1000 for axis in ['VX', 'VY', 'VZ']]
    return {'spacecraft': spacecraft, 'frame_id': frame, 'origin': origin, 'axes': axes, 'epoch_utc': utc_iso(utc), 'native_utc_gregorian': utc, 'native_tai_gregorian': tai, 'epoch_tai_gmat_mod_julian': finite(tai_mjd), 'epoch_utc_gmat_mod_julian': finite(utc_mjd), 'position_m': position, 'velocity_m_s': velocity}


def norm(vector):
    return math.sqrt(sum(finite(x)**2 for x in vector))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def osculating(state, mu_m3_s2):
    r, v = state['position_m'], state['velocity_m_s']
    radius, speed = norm(r), norm(v)
    mu = finite(mu_m3_s2)
    if radius <= 0 or mu <= 0:
        raise EvidenceError('Invalid body-relative state or gravitational parameter')
    rv = dot(r, v)
    energy = speed**2/2 - mu/radius
    eccentricity = norm([((speed**2-mu/radius)*x-rv*y)/mu for x, y in zip(r, v)])
    h = [r[1]*v[2]-r[2]*v[1], r[2]*v[0]-r[0]*v[2], r[0]*v[1]-r[1]*v[0]]
    return {'radius_m': radius, 'speed_m_s': speed, 'radial_velocity_m_s': rv/radius, 'specific_energy_m2_s2': energy, 'eccentricity': eccentricity, 'osculating_periapsis_radius_m': norm(h)**2/mu/(1+eccentricity)}


# These tolerances are extraction/event checks, not an accuracy claim.
REFERENCE_POLICY = {
    'id': 'clavius-gmat-reference-checks-v1',
    'encounter_radial_velocity_tolerance_m_s': .01,
    'encounter_osculating_periapsis_tolerance_m': 1.,
    'same_epoch_tolerance_s': .01,
    'same_position_tolerance_m': .01,
    'impulse_magnitude_tolerance_m_s': 1e-5,
    'guard_time_margin_s': 1., 'guard_radius_margin_m': 1.,
    'full_trajectory_clearance_checked': False,
    'tighter_repropagation_checked': False,
}


def endpoint_checks(states, bodies, burns, guards, expected_post_days):
    moon_mu = finite(bodies['Luna']['Mu'])*1e9
    moon_radius = finite(bodies['Luna']['EquatorialRadius'])*1000
    earth_radius = finite(bodies['Earth']['EquatorialRadius'])*1000
    if min(moon_radius, earth_radius) <= 0:
        raise EvidenceError('Invalid native body radius')
    for label, state in states.items():
        expected = 'Earth' if label == 'departure_earth' else 'Luna'
        if state['origin'] != expected:
            raise EvidenceError('Wrong central body for ' + label)
    dep, enc, cap, post = (states[name] for name in ['departure_earth', 'encounter_moon', 'capture_moon', 'post_capture_moon'])
    duration = (enc['epoch_tai_gmat_mod_julian'] - dep['epoch_tai_gmat_mod_julian'])*86400
    capture_offset = (cap['epoch_tai_gmat_mod_julian'] - enc['epoch_tai_gmat_mod_julian'])*86400
    coast = (post['epoch_tai_gmat_mod_julian'] - cap['epoch_tai_gmat_mod_julian'])*86400
    orbital = {name: osculating(states[name], moon_mu) for name in ['encounter_moon', 'capture_moon', 'post_capture_moon']}
    loi = burns['LOI']
    if loi['CoordinateSystem'] != 'Local' or loi['Origin'] != 'Luna' or loi['Axes'] != 'VNB':
        raise EvidenceError('Unexpected reference insertion-burn frame')
    impulse = norm([finite(loi['Element'+str(i)])*1000 for i in [1, 2, 3]])
    observed_impulse = norm([x-y for x, y in zip(cap['velocity_m_s'], enc['velocity_m_s'])])
    checks = {
        'positive_transfer_duration': duration > 0,
        'encounter_stationary_radius': abs(orbital['encounter_moon']['radial_velocity_m_s']) <= REFERENCE_POLICY['encounter_radial_velocity_tolerance_m_s'],
        'encounter_at_osculating_periapsis': abs(orbital['encounter_moon']['radius_m']-orbital['encounter_moon']['osculating_periapsis_radius_m']) <= REFERENCE_POLICY['encounter_osculating_periapsis_tolerance_m'],
        'capture_same_epoch': abs(capture_offset) <= REFERENCE_POLICY['same_epoch_tolerance_s'],
        'capture_same_position': cap['frame_id'] == enc['frame_id'] and norm([x-y for x, y in zip(cap['position_m'], enc['position_m'])]) <= REFERENCE_POLICY['same_position_tolerance_m'],
        'insertion_impulse_matches': abs(observed_impulse-impulse) <= REFERENCE_POLICY['impulse_magnitude_tolerance_m_s'],
        'departure_outside_earth_sphere': norm(dep['position_m']) > earth_radius,
        'post_capture_duration_matches_source': abs(coast-expected_post_days*86400) <= REFERENCE_POLICY['same_epoch_tolerance_s'],
    }
    for label, orbit in orbital.items():
        checks[label+'_outside_lunar_sphere'] = orbit['radius_m'] > moon_radius
        if label != 'encounter_moon':
            checks[label+'_negative_energy'] = orbit['specific_energy_m2_s2'] < 0
            checks[label+'_elliptic'] = orbit['eccentricity'] < 1
            checks[label+'_osculating_periapsis_clear'] = orbit['osculating_periapsis_radius_m'] > moon_radius
    if 'maximum_elapsed_days' in guards:
        checks['encounter_before_time_guard'] = duration < guards['maximum_elapsed_days']*86400-REFERENCE_POLICY['guard_time_margin_s']
    if 'minimum_radius_km' in guards:
        checks['encounter_above_radius_guard'] = orbital['encounter_moon']['radius_m'] > guards['minimum_radius_km']*1000+REFERENCE_POLICY['guard_radius_margin_m']
    return {'policy': REFERENCE_POLICY, 'passed': all(checks.values()), 'checks': checks, 'orbital_elements': orbital, 'transfer_duration_s': duration, 'capture_offset_s': capture_offset, 'post_capture_duration_s': coast, 'native_moon_radius_m': moon_radius, 'native_earth_radius_m': earth_radius, 'observed_insertion_impulse_m_s': observed_impulse, 'declared_insertion_impulse_m_s': impulse}
