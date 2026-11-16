"""Reduce Chrono solver states to trailing 50 ms wheel measurements."""
import numpy as np
from scipy.spatial.transform import Rotation

RADIUS_M = .25
MIN_LOAD_N = 1.
MIN_RIM_M_S = .02
CHANNELS = ["mean_normal_load_n", "loaded_fraction", "rim_m_s", "along_m_s", "lateral_m_s"]


def dot(a, b):
    return np.sum(a*b, axis=-1)


def terrain_normals(grid, centers):
    """Upward normal to the same triangle used by the rigid collision mesh."""
    xy = centers[..., :2]/5
    i, j = np.floor(xy).astype(int).T
    if np.any((i < -2) | (i > 1) | (j < -2) | (j > 1)):
        raise ValueError("Wheel outside native collision mesh")
    first = np.sum(xy - np.floor(xy), axis=-1) <= 1
    i, j = i+256, j+256
    a, b, c, d = grid[j,i], grid[j,i+1], grid[j+1,i], grid[j+1,i+1]
    normal = np.column_stack((-np.where(first,b-a,d-c)/5, -np.where(first,c-a,d-b)/5, np.ones(len(i))))
    return normal / np.linalg.norm(normal, axis=1)[:, None]


def reduce_wheel(states, grid):
    pos, velocity, omega, axle, force = np.moveaxis(states, 1, 0)
    normal = terrain_normals(grid, pos)
    forward = np.cross(axle, normal)
    forward /= np.linalg.norm(forward, axis=1)[:, None]
    load = np.maximum(0, dot(force, normal)).reshape(-1,50)
    loaded = load > MIN_LOAD_N
    count = loaded.sum(axis=1)
    lateral = np.cross(normal, forward)
    speeds = []
    for values in [RADIUS_M*dot(omega,axle), dot(velocity,forward), dot(velocity,lateral)]:
        total = np.sum(np.where(loaded,values.reshape(-1,50),0),axis=1)
        speeds.append(np.divide(total,count,out=np.full(len(count),np.nan),where=count>0))
    return np.column_stack([load.mean(axis=1),count/50,*speeds])


def build_wheels(raw, grid_path, poses, target):
    states = np.fromfile(raw,dtype="<f4").reshape(20000,4,5,3).astype(float)
    if not np.isfinite(states).all():
        raise ValueError("Nonfinite native wheel state")
    grid = np.fromfile(grid_path,dtype="<f4").reshape(513,513).astype(float)
    rows = np.full((401,4,len(CHANNELS)),np.nan,dtype="<f4")
    hub_error = angle_error = 0.
    for corner, part in enumerate([4,8,12,16]):
        wheel = states[:,corner]
        rows[1:,corner] = reduce_wheel(wheel,grid)
        if not np.array_equal(wheel[49::50,0],poses[1:,part,:3]):
            raise ValueError("Native wheel samples out of sync with poses")
        # Integrate world velocities separately and compare with shipped CAD pose
        # differences over each 50 ms interval after the drive reaches speed.
        steady = wheel[4000:]
        distance = .001*steady[:,1].reshape(-1,50,3).sum(axis=1)
        delta = np.diff(poses[80:,part,:3],axis=0)
        hub_error = max(hub_error,float(np.max(np.linalg.norm(distance-delta,axis=1))))
        turns = Rotation.from_quat(poses[80:,part,3:])
        rotvec = (turns[1:]*turns[:-1].inv()).as_rotvec()
        angles = .001*steady[:,2].reshape(-1,50,3).sum(axis=1)
        angle_error = max(angle_error,float(np.max(np.linalg.norm(angles-rotvec,axis=1))))
    if hub_error > .001 or angle_error > .01:
        raise ValueError(f"Wheel pose/velocity check failed: {hub_error=} {angle_error=}")
    rows.tofile(target)
    return dict(interval_s=[4,20],max_hub_interval_residual_m=hub_error,
                max_rotation_interval_residual_rad=angle_error,limits_m_rad=[.001,.01])
