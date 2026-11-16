"""Targeted, zero-revolution patched-conic flight rehearsal in km and SI seconds."""
import math

import numpy as np
import spiceypy as spice
from pydantic import BaseModel, Field
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .geometry import _lock, utc_from_et
from .drive_environment import start_epoch, drive_sources
from .mission import Cancelled
from .provenance import implementation
from .terrain import SiteId, site

EARTH_MU, MOON_MU = 398600.4418, 4902.8001
EARTH_RADIUS = 6378.137
APPROACH_HEIGHT = 100.0
DESCENT_SECONDS = 900.0


class FlightRequest(BaseModel):
    site_id: SiteId
    departure_utc: str = Field(max_length=40)
    transfer_hours: float = Field(default=96, ge=72, le=120, allow_inf_nan=False)


def unit(v):
    return v / np.linalg.norm(v)


def stumpff(z):
    if abs(z) < 1e-5:
        return .5-z/24+z*z/720, 1/6-z/120+z*z/5040
    w = math.sqrt(abs(z))
    if z > 0:
        return (1-math.cos(w))/z, (w-math.sin(w))/w**3
    return (math.cosh(w)-1)/(-z), (math.sinh(w)-w)/w**3


def coast(start, end, duration, mu, floor_km):
    """Short-way Lambert solution checked by independent Cartesian integration."""
    r1, r2 = np.linalg.norm(start), np.linalg.norm(end)
    angle_cos = np.clip(unit(start) @ unit(end), -1, 1)
    a = math.sqrt(r1*r2*(1+angle_cos))

    def transfer(z):
        c, s = stumpff(z)
        y = r1+r2+a*(z*s-1)/math.sqrt(c)
        if y <= 0:
            return -duration
        return ((y/c)**1.5*s+a*math.sqrt(y))/math.sqrt(mu)-duration

    lower = -1.
    while transfer(lower) > 0 and lower > -256:
        lower *= 2
    z = brentq(transfer, lower, (2*math.pi-.001)**2, xtol=1e-12)
    c, s = stumpff(z)
    y = r1+r2+a*(z*s-1)/math.sqrt(c)
    velocity = (end-(1-y/r1)*start)/(a*math.sqrt(y/mu))

    def derivative(t, state):
        r = state[:3]
        return np.r_[state[3:], -mu*r/np.linalg.norm(r)**3]

    def apsis(t, state):
        return state[:3] @ state[3:]

    sol = solve_ivp(derivative, [0, duration], np.r_[start, velocity], method='DOP853',
                    events=apsis, t_eval=np.linspace(0, duration, 181), rtol=2e-11, atol=1e-11)
    if not sol.success or np.linalg.norm(sol.y[:3, -1]-end) > .01:
        raise ValueError('Transfer missed its approach target by more than 10 m.')
    closest = min(r1, r2, *(np.linalg.norm(row[:3]) for row in sol.y_events[0]))
    if closest <= floor_km:
        raise ValueError('The coast intersects its central-body reference sphere.')
    return sol, closest


def moon_state(et):
    with _lock:
        return np.asarray(spice.spkezr('MOON', et, 'J2000', 'NONE', 'EARTH')[0])


def globe_frames(start, times):
    """Body-fixed to J2000 rotations (quaternions in Three.js xyzw order)."""
    result = {'earth_xyzw': [], 'moon_xyzw': [], 'sun_direction_j2000': []}
    with _lock:
        for offset in times:
            et = start + offset
            for name, frame in [('earth_xyzw', 'IAU_EARTH'), ('moon_xyzw', 'MOON_ME_DE421')]:
                w, x, y, z = spice.m2q(spice.pxform(frame, 'J2000', et))
                result[name].append([x, y, z, w])
            sunlight, _ = spice.spkpos('SUN', et, 'J2000', 'NONE', 'EARTH')
            result['sun_direction_j2000'].append(unit(sunlight).tolist())
    return result


def flight_samples(earth, moon, start, patch_time, gate, ground):
    """Earth-centered J2000 states. At each impulse store the outbound velocity."""
    times = np.concatenate((earth.t, patch_time-start+moon.t[1:], gate-start+np.arange(30., DESCENT_SECONDS+1, 30.)))
    lunar = np.array([moon_state(start+t) for t in times])
    patch = len(earth.t)-1
    approach = patch+len(moon.t)-1
    craft = np.empty_like(lunar)
    craft[:patch+1] = earth.y.T
    craft[patch, 3:] = lunar[patch, 3:] + moon.y[3:, 0]
    craft[patch+1:approach+1] = lunar[patch+1:approach+1] + moon.y.T[1:]
    radial = unit(ground)
    for i in range(approach, len(times)):
        fraction = max(0., 1-(times[i]-times[approach])/DESCENT_SECONDS)
        fixed = np.r_[ground+APPROACH_HEIGHT*fraction**2*radial,
                      -2*APPROACH_HEIGHT/DESCENT_SECONDS*fraction*radial]
        with _lock:
            transform = spice.sxform('MOON_ME_DE421', 'J2000', start+times[i])
        state = lunar[i] + transform @ fixed
        if i == approach:
            # Preserve the independently integrated coast endpoint at the brake.
            craft[i, 3:] = state[3:]
        else:
            craft[i] = state
    return {'globe_frames': globe_frames(start, times), 'times_seconds': times.tolist(), 'spacecraft_coords_km': craft[:, :3].tolist(),
            'spacecraft_velocities_kms': craft[:, 3:].tolist(), 'moon_coords_km': lunar[:, :3].tolist(),
            'moon_velocities_kms': lunar[:, 3:].tolist(), 'patch_index': patch, 'approach_index': approach,
            'lunar_reference_radius_km': 1737.4, 'earth_reference_radius_km': EARTH_RADIUS,
            'earth_mu_km3_s2': EARTH_MU}


def plan_flight(request, progress, cancel):
    start = start_epoch(request.departure_utc)
    duration = request.transfer_hours*3600
    gate = start+duration
    landed = gate+DESCENT_SECONDS
    if utc_from_et(landed)[:4] >= '2050':
        raise ValueError('Arrival exceeds the supported 2049 date range.')
    terrain = site(request.site_id)
    ground = terrain.origin/1000
    radial = unit(ground)
    with _lock:
        transform = np.asarray(spice.sxform('MOON_ME_DE421', 'J2000', gate))
    gate_fixed = ground+APPROACH_HEIGHT*radial
    # A prescribed rotating-frame radial descent h(t)=H(1-t/T)^2.
    descent_entry = transform @ np.r_[gate_fixed, -2*APPROACH_HEIGHT/DESCENT_SECONDS*radial]
    patch_time = gate-18*3600
    patch_moon = moon_state(patch_time)
    patch = 50000*unit(-unit(patch_moon[:3])+.65*unit(descent_entry[:3]))
    destination = patch_moon[:3]+patch
    normal = unit(np.cross(patch_moon[:3], patch_moon[3:]))
    tangent = unit(np.cross(normal, destination))
    angle = math.radians(155)
    parking = (EARTH_RADIUS+200)*(math.cos(angle)*unit(destination)-math.sin(angle)*tangent)
    progress(.15, 'Solving Earth departure')
    if cancel():
        raise Cancelled()
    earth, earth_min = coast(parking, destination, patch_time-start, EARTH_MU, EARTH_RADIUS)
    progress(.55, 'Targeting lunar approach')
    moon, moon_min = coast(patch, descent_entry[:3], gate-patch_time, MOON_MU, np.linalg.norm(ground))
    plane = unit(np.cross(parking, earth.y[3:, 0]))
    circular = math.sqrt(EARTH_MU/np.linalg.norm(parking))*np.cross(plane, unit(parking))
    impulses = {
        'injection': float(np.linalg.norm(earth.y[3:, 0]-circular)),
        'patch_correction': float(np.linalg.norm(moon.y[3:, 0]+patch_moon[3:]-earth.y[3:, -1])),
        'descent_braking': float(np.linalg.norm(descent_entry[3:]-moon.y[3:, -1])),
    }
    # Radial thrust integral, neglecting rotation in the thrust estimate.
    t = np.linspace(0, DESCENT_SECONDS, 129)
    height = APPROACH_HEIGHT*(1-t/DESCENT_SECONDS)**2
    accel = MOON_MU/(np.linalg.norm(ground)+height)**2+2*APPROACH_HEIGHT/DESCENT_SECONDS**2
    impulses['powered_descent'] = float(np.trapezoid(accel,t))
    samples = flight_samples(earth, moon, start, patch_time, gate, ground)
    return {
        'request': request.model_dump(), 'departure_utc': utc_from_et(start),
        'landing': {'site_id': terrain.id, 'name': terrain.name, 'latitude_deg': terrain.lat,
                    'longitude_deg': terrain.lon, 'elevation_m': terrain.origin_height_m,
                    'east_m': 0., 'north_m': 0., 'utc': utc_from_et(landed),
                    'frame': 'MOON_ME_DE421', 'terrain_realization_id': 'nominal'},
        'transfer_s': landed-start, 'maneuvers_km_s': impulses, 'total_delta_v_km_s': sum(impulses.values()),
        'trajectory_3d': samples,
        'trajectory_earth_j2000_km': samples['spacecraft_coords_km'][:samples['approach_index']+1], 'patch_index': len(earth.t)-1,
        'approach_utc': utc_from_et(gate), 'approach_height_km': APPROACH_HEIGHT,
        'descent_s': DESCENT_SECONDS, 'terminal_surface_speed_m_s': 0.,
        'endpoint_residual_m': [float(1000*np.linalg.norm(earth.y[:3,-1]-destination)),
                                float(1000*np.linalg.norm(moon.y[:3,-1]-descent_entry[:3]))],
        'minimum_central_radius_km': [earth_min, moon_min],
        'model': 'Two targeted point-mass coasts with a patch impulse, followed by a prescribed powered vertical descent. Departure from a selectable-epoch 200 km circular parking orbit with a freely chosen plane. No launch-pad, vehicle thrust, fuel, landing dispersion or hazard qualification.',
        'sources': drive_sources(terrain), 'provenance': {'implementation': implementation()},
    }

def saved_flight_samples(flight):
    if 'trajectory_3d' in flight:
        samples = flight['trajectory_3d']
        if 'globe_frames' in samples:
            return samples
        start = start_epoch(flight['request']['departure_utc'])
        return {**samples, 'globe_frames': globe_frames(start, samples['times_seconds'])}
    # Older runs saved positions only. Recover the missing states without changing
    # the saved artifact, and verify the full original coast before using them.
    recovered = plan_flight(FlightRequest(**flight['request']), lambda *_: None, lambda: False)
    original = np.asarray(flight['trajectory_earth_j2000_km'])
    replayed = np.asarray(recovered['trajectory_earth_j2000_km'])
    if (original.shape != replayed.shape or not np.allclose(original, replayed, rtol=0, atol=1e-5)
            or recovered['landing'] != flight['landing']):
        raise ValueError('The saved trajectory could not be reproduced. Calculate a new flight to view its telemetry.')
    return recovered['trajectory_3d']
