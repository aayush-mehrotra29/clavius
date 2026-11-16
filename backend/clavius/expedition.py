"""Bind one solved flight, native rover trace and dated surface energy ledger."""
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.spatial.transform import Rotation

from .drive_environment import drive_sample, drive_sources
from .dynamics import SegmentRequest, simulate_segment
from .geometry import epoch, utc_from_et
from .mission import integrate_energy
from .terrain import site


class Target(BaseModel):
    east_m: float = Field(ge=-12, le=12, allow_inf_nan=False)
    north_m: float = Field(ge=-12, le=12, allow_inf_nan=False)


class TraverseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    flight_id: str
    robot_id: str
    waypoints: list[Target] = Field(min_length=1, max_length=5)
    task: Literal['science', 'wait']
    dwell_s: int = Field(default=5, ge=1, le=30)


class WaypointDriver:
    tolerance_m = .18

    def __init__(self, request, speed):
        self.route = request.waypoints
        self.task = request.task
        self.dwell_s = request.dwell_s
        self.speed = speed
        self.index = 0
        self.events = []
        self.activity = 'drive'
        self.task_start = None
        self.finished = False

    def command(self, t, east, north, yaw):
        target = self.route[self.index]
        dx, dy = target.east_m-east, target.north_m-north
        distance = math.hypot(dx, dy)
        # Stop inside the dwell circle. Braking exactly at its boundary caused
        # small contact oscillations to restart otherwise stationary tasks.
        arrival_radius = self.tolerance_m if self.task_start is not None else self.tolerance_m*.5
        if distance <= arrival_radius:
            if self.index+1 < len(self.route):
                self.events.append({'t_s': t, 'waypoint': self.index+1})
                self.index += 1
                return 0., 0.
            if self.task_start is None:
                self.task_start = t
            self.activity = self.task
            if t-self.task_start >= self.dwell_s:
                self.events.append({'t_s': t, 'waypoint': self.index+1, 'completed_task': self.task})
                self.finished = True
            return 0., 0.
        self.task_start = None
        self.activity = 'drive'
        error = math.remainder(math.atan2(dy, dx)-yaw, 2*math.pi)
        turn = float(np.clip(1.6*error, -.2, .2))
        return min(self.speed, distance*.6)*max(0., math.cos(error))**4, turn


def traverse(request, flight, robot, progress, cancel):
    landing = flight['landing']
    terrain = site(landing['site_id'], landing['terrain_realization_id'])
    start = epoch(landing['utc'])
    speed = min(.10, robot['profile']['mobility']['nominal_speed_m_s'])
    driver = WaypointDriver(request, speed)
    first = request.waypoints[0]
    segment = SegmentRequest(robot_id=robot['id'], site_id=terrain.id,
                             east_m=landing['east_m'], north_m=landing['north_m'],
                             heading_deg=math.degrees(math.atan2(first.north_m-landing['north_m'],
                                                                first.east_m-landing['east_m'])),
                             duration_s=180, speed_m_s=speed)
    power = robot['profile']['power']
    capacity = power['battery_capacity_wh']
    energy = minimum = capacity*power['initial_soc_fraction']
    previous = 0.
    previous_bus_wh = 0.
    next_sky = 0.
    sky = None
    depleted = False

    def energy_step(row):
        nonlocal sky, next_sky, previous, previous_bus_wh, energy, minimum, depleted
        # Zero-order hold between terrain horizon evaluations at actual rover poses.
        if row['t_s'] >= next_sky or sky is None:
            sky = drive_sample(terrain, start+row['t_s'], row['east_m'], row['north_m'])
            next_sky = row['t_s']+5.
        normal = Rotation.from_quat(row['quaternion_xyzw']).apply(power['array_normal_body_unit'])
        solar = (power['solar_rated_power_w']*(149597870.7/sky['sun_distance_km'])**2
                 *max(0., float(normal @ sky['sun_site_enu']))*sky['disk_fraction'])
        interval_s = row['t_s']-previous
        drive_load = (row['mobility_bus_energy_wh']-previous_bus_wh)*3600/interval_s
        previous_bus_wh = row['mobility_bus_energy_wh']
        load = drive_load + (power['science_increment_w'] if row['activity']=='science' else 0)
        energy,_ = integrate_energy(energy,solar,load,interval_s,capacity,
                                    power['charge_efficiency'],power['discharge_efficiency'])
        minimum = min(minimum,energy)
        previous = row['t_s']
        row.update(utc=utc_from_et(start+row['t_s']),battery_wh=energy,solar_w=solar,sun_enu=sky['sun_site_enu'],
                   disk_fraction=sky['disk_fraction'],earth_visible=sky['earth_center_visible'])
        depleted = energy <= 0 and solar < load
        return depleted

    result = simulate_segment(segment, robot, progress, cancel, controller=driver, observe_frame=energy_step)
    trace = result['trace']
    issues = [e['message'] for e in result['events']]
    if depleted:
        issues.append('Battery depleted. Wheel commands and task execution stopped.')
    elif not driver.finished:
        issues.append('The rover did not finish the route and dwell within 180 s.')
    if minimum < power['reserve_wh']:
        issues.append('Battery energy crossed the declared reserve.')
    if not result['metrics']['contacts_observed']:
        issues.append('No rigid contact was recorded.')
    return {'flight_id':flight['id'], 'flight_sha256':flight['artifact_sha256'], 'landing':landing,
            'request':request.model_dump(), 'engine':result['engine'], 'robot_id':robot['id'],
            'robot_package_sha256':robot['package_sha256'], 'robot_snapshot':robot,
            'provenance':result['provenance'], 'sources':drive_sources(terrain),
            'trace':trace, 'route_events':[e for e in driver.events if not (depleted and 'completed_task' in e)],
            'task_completed':driver.finished and not depleted,
            'issues':issues, 'metrics':{**result['metrics'],'minimum_battery_wh':minimum,
                                      'battery_capacity_wh':capacity,'arrival_tolerance_m':driver.tolerance_m}}
