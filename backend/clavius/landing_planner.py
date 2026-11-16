"""Bounded site, landing-date and transfer search over the curated terrain origins."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from . import store
from .drive_environment import drive_sample, drive_sources, start_epoch
from .flight import DESCENT_SECONDS, FlightRequest, plan_flight
from .geometry import utc_from_et
from .mission import Cancelled
from .paths import RUNTIME
from .provenance import implementation
from .terrain import catalogue, site


class LandingSearch(BaseModel):
    landing_utc: str = Field(max_length=40)
    date_spacing_days: int = Field(default=7, ge=1, le=90)
    surface_hours: int = Field(default=24, ge=1, le=720)
    priority: Literal['balanced', 'sunlight', 'contact', 'delta_v'] = 'balanced'
    array_mount: Literal['level', 'tracking'] = 'level'
    min_sun_hours: float = Field(default=0, ge=0, le=720, allow_inf_nan=False)
    max_outage_hours: float | None = Field(default=None, ge=0, le=720, allow_inf_nan=False)
    max_slope_deg: float | None = Field(default=None, ge=0, le=90, allow_inf_nan=False)
    max_delta_v_km_s: float | None = Field(default=None, gt=0, allow_inf_nan=False)


TRANSFER_HOURS = (72, 96, 120)


def windows(rows, clearance_key):
    """Positive clearance intervals; linearly interpolate bracketed crossings."""
    result = []
    start = 0 if rows[0][clearance_key] > 0 else None
    for left, right in zip(rows, rows[1:]):
        a, b = left[clearance_key], right[clearance_key]
        if (a > 0) == (b > 0):
            continue
        t = left['t_s'] + (right['t_s'] - left['t_s']) * a / (a - b)
        if b > 0:
            start = t
        else:
            result.append([start, t])
            start = None
    if start is not None:
        result.append([start, rows[-1]['t_s']])
    return result


def longest_gap(intervals, duration):
    end = 0
    longest = 0
    for start, stop in intervals:
        longest = max(longest, start-end)
        end = stop
    return max(longest, duration-end)


def surface_window(terrain, start, hours, cancel):
    duration = hours * 3600
    step = 600 if hours <= 72 else 1800
    rows = []
    for elapsed in range(0, duration+1, step):
        if cancel():
            raise Cancelled()
        s = drive_sample(terrain, start+elapsed, 0, 0)
        irradiance = 1361 * (149597870.7 / s['sun_distance_km'])**2 * s['disk_fraction']
        rows.append({
            'utc':s['utc'], 't_s': elapsed, **{k:s[k] for k in ('sun_azimuth_deg','earth_azimuth_deg','sun_elevation_deg',
                'earth_elevation_deg','sun_horizon_deg','earth_horizon_deg','disk_fraction')},
            'sun_limb_clearance_deg': s['sun_elevation_deg'] + s['sun_angular_radius_deg'] - s['sun_horizon_deg'],
            'earth_center_clearance_deg': s['earth_elevation_deg'] - s['earth_horizon_deg'],
            'tracking_irradiance_w_m2': irradiance,
            'level_irradiance_w_m2': irradiance * max(0, math.sin(math.radians(s['sun_elevation_deg']))),
        })
    def integral(key):
        return sum((a[key]+b[key])*.5*(b['t_s']-a['t_s'])/3600 for a,b in zip(rows,rows[1:]))
    sunlight = windows(rows, 'sun_limb_clearance_deg')
    contact = windows(rows, 'earth_center_clearance_deg')
    return {
        'samples':rows, 'sample_step_s':step, 'sun_windows_s':sunlight, 'contact_windows_s':contact,
        'sun_windows_utc':[[utc_from_et(start+a),utc_from_et(start+b)] for a,b in sunlight],
        'contact_windows_utc':[[utc_from_et(start+a),utc_from_et(start+b)] for a,b in contact],
        'sun_hours':sum(b-a for a,b in sunlight)/3600, 'equivalent_sun_hours':integral('disk_fraction'),
        'tracking_solar_wh_m2':integral('tracking_irradiance_w_m2'), 'level_solar_wh_m2':integral('level_irradiance_w_m2'),
        'contact_hours':sum(b-a for a,b in contact)/3600, 'longest_outage_hours':longest_gap(contact,duration)/3600,
    }


def exclusions(row, request):
    limits = [(row['equivalent_sun_hours'] < request.min_sun_hours, 'Insufficient equivalent sunlight')]
    for key, limit, reason in [('longest_outage_hours',request.max_outage_hours,'Earth outage exceeds limit'),
                               ('slope_deg', request.max_slope_deg,'Slope exceeds limit'),
                               ('delta_v_km_s', request.max_delta_v_km_s,'Transfer Δv exceeds limit')]:
        limits.append((limit is not None and row[key] > limit, reason))
    return [reason for failed, reason in limits if failed]


def ranked_options(candidates, request):
    eligible = [r for r in candidates if 'unavailable' not in r and not r['exclusions']]
    energy_key = request.array_mount + '_solar_wh_m2'
    max_energy = max((r[energy_key] for r in eligible), default=0)
    max_contact = max((r['contact_hours'] for r in eligible), default=0)
    def order(row):
        sun = row[energy_key]/max_energy if max_energy else 0
        contact = row['contact_hours']/max_contact if max_contact else 0
        dv = row['delta_v_km_s']
        primary = {'sunlight':sun, 'contact':contact, 'delta_v':-dv, 'balanced':min(sun, contact)}
        return (-primary[request.priority], -(sun+contact), dv, row['slope_deg'], row['key'])
    return [r['key'] for r in sorted(eligible, key=order)]


def search_landings(request, progress, cancel):
    start_epoch(request.landing_utc)  # Enforce supported and timezone-aware input.
    first = datetime.fromisoformat(request.landing_utc.replace('Z','+00:00')).astimezone(timezone.utc)
    dates = [(first+timedelta(days=i*request.date_spacing_days)).isoformat().replace('+00:00','Z') for i in range(3)]
    sites = catalogue()
    candidates, evidence = [], {}
    for entry in sites:
        identity = entry['id']
        for index, stamp in enumerate(dates):
            progress(len(candidates)/(len(sites)*len(dates)), f"Checking {entry['name']} · {stamp[:10]}")
            row = {'key':f'{identity}-{index}', 'site_id':identity, 'name':entry['name'], 'landing_utc':stamp, 'paths':[]}
            candidates.append(row)
            try:
                start = start_epoch(stamp)
                if utc_from_et(start+request.surface_hours*3600)[:4] >= '2050':
                    raise ValueError('Surface evaluation extends beyond the supported date range.')
                terrain = site(identity)
                if identity not in evidence:
                    azimuths = list(range(0,360,4))
                    skyline = terrain.horizon_directions(0,0,azimuths,.5)
                    point = terrain.sample(0, 0)
                    def finite(key):
                        value = float(point[key])
                        return value if math.isfinite(value) else None
                    evidence[identity] = {**drive_sources(terrain), 'skyline_step_deg':4,
                        'height_rms_m':finite('height_rms_m'), 'native_return_count':finite('nominal_lola_return_count'),
                        'support_sha256':{a['id']:a['sha256'] for a in terrain.manifest['assets']
                                          if a['id'] in (terrain.definition['error_asset_id'],terrain.definition['count_asset_id'])},
                        'skyline_deg':skyline.tolist(), 'latitude_deg':terrain.lat, 'longitude_deg':terrain.lon}
                row['slope_deg'] = float(terrain.slope(0,0))
                row.update(surface_window(terrain, start, request.surface_hours, cancel))
                best = None
                for hours in TRANSFER_HOURS:
                    if cancel():
                        raise Cancelled()
                    departure = utc_from_et(start - DESCENT_SECONDS - hours*3600)
                    path = {'transfer_hours':hours, 'departure_utc':departure}
                    row['paths'].append(path)
                    try:
                        flight = plan_flight(FlightRequest(site_id=identity, departure_utc=departure, transfer_hours=hours),
                                             lambda *_:None, cancel)
                    except ValueError as exc:
                        path['unavailable'] = str(exc)
                        continue
                    path['delta_v_km_s'] = flight['total_delta_v_km_s']
                    if best is None or path['delta_v_km_s'] < best['total_delta_v_km_s']:
                        best = flight
                if best is None:
                    raise ValueError('No evaluated transfer reached this landing.')
                row.update(delta_v_km_s=best['total_delta_v_km_s'], transfer_hours=best['request']['transfer_hours'],
                           flight_sha256=store.artifact(best), departure_utc=best['departure_utc'])
                row['exclusions'] = exclusions(row, request)
            except (ValueError, FileNotFoundError) as exc:
                row['unavailable'] = str(exc)
    return {'request':request.model_dump(), 'candidates':candidates, 'ranked_keys':ranked_options(candidates, request),
            'sites':evidence, 'transfer_hours':list(TRANSFER_HOURS), 'model':'nominal-landing-search-v1',
            'provenance':implementation()}


def selected_flight(plan, key):
    candidate = next((r for r in plan['candidates'] if r['key']==key),None)
    if not candidate or key not in plan['ranked_keys']:
        raise ValueError('Choose an evaluated option that meets the planning limits.')
    digest = candidate['flight_sha256']
    raw = (RUNTIME/'artifacts'/f'{digest}.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Saved transfer failed its integrity check.')
    identity = str(uuid5(NAMESPACE_URL, f"clavius:landing:{plan['id']}:{key}"))
    existing = store.get(identity)
    if existing is not None:
        return existing
    flight = json.loads(raw)
    request = plan['request']
    selection = {'plan_id':plan['id'], 'candidate_key':key, 'solved_flight_sha256':digest,
                 'rank':plan['ranked_keys'].index(key)+1,'priority':request['priority'],
                 'surface_hours':request['surface_hours'],'array_mount':request['array_mount'],
                 'incident_wh_m2':candidate[request['array_mount']+'_solar_wh_m2'],
                 **{k:candidate[k] for k in ('equivalent_sun_hours','contact_hours','longest_outage_hours','slope_deg')}}
    result = {**flight, 'planning_selection':selection}
    return store.put('expedition', {**result, 'artifact_sha256':store.artifact(result), 'kind':'flight'}, identity)
