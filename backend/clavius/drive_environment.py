"""Geometric sunlight and Earth visibility at a nominal VIPER drive position."""
from datetime import datetime, timezone
import numpy as np

from .geometry import directions, epoch, solar_disk_fraction, utc_from_et
from .integrity import verify_sources
from .terrain import basis, site, TerrainCoverageError

MODEL = "clavius-drive-directional-horizon-v1"
OBSERVER_HEIGHT_M = .5


def start_epoch(utc):
    stamp = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("The start time must include a UTC offset.")
    stamp = stamp.astimezone(timezone.utc)
    if not 2000 <= stamp.year <= 2049:
        raise ValueError("Choose a UTC start from 2000 through 2049.")
    return epoch(stamp.isoformat().replace("+00:00", "Z"))


def drive_sources(terrain):
    keys = (terrain.definition["local_asset_id"], terrain.definition["regional_asset_id"])
    return {
        "terrain_sha256": {a["id"]: a["sha256"] for a in terrain.manifest["assets"] if a["id"] in keys},
        "kernel_sha256": {a["file"]: a["sha256"] for a in verify_sources("kernels")["assets"]},
        "frame": "MOON_ME_DE421", "aberration": "NONE", "realization": "nominal",
        "observer_height_m": OBSERVER_HEIGHT_M, "max_ray_distance_m": 220000,
    }


def drive_sample(terrain, et, east, north):
    point = terrain.sample(east, north)
    if not point["covered"]:
        raise TerrainCoverageError("The observer lies outside the nominal local terrain.")
    lat, lon = float(point["lat_deg"]), float(point["lon_deg"])
    geometry = directions(et, lat, lon, float(point["elevation_m"]) + OBSERVER_HEIGHT_M)
    sun, earth = geometry["sun"], geometry["earth"]
    sh, eh = terrain.horizon_directions(east, north, [sun["azimuth_deg"], earth["azimuth_deg"]], OBSERVER_HEIGHT_M)
    # At a polar site the observer's geographic north can rotate appreciably
    # during a traverse. The scene retains its fixed nominal ENU basis.
    site_enu = (np.asarray(sun["enu"]) @ basis(lat, lon).T) @ terrain.rotation
    return {
        "utc": utc_from_et(et), "east_m": east, "north_m": north,
        "sun_site_enu": site_enu.tolist(), "sun_azimuth_deg": sun["azimuth_deg"],
        "sun_elevation_deg": sun["elevation_deg"], "sun_horizon_deg": float(sh),
        "sun_angular_radius_deg": sun["angular_radius_deg"],
        "disk_fraction": solar_disk_fraction(sun["elevation_deg"], float(sh), sun["angular_radius_deg"]),
        "earth_elevation_deg": earth["elevation_deg"], "earth_horizon_deg": float(eh),
        "earth_center_visible": earth["elevation_deg"] > float(eh),
    }


def live_sample(identity, start_utc, elapsed, east, north):
    terrain = site(identity)
    et = start_epoch(start_utc) + elapsed
    if et >= epoch("2050-01-01T00:00:00Z"):
        raise ValueError("The sample time exceeds the supported kernel interval.")
    return {"model": MODEL, "site_id": identity, "elapsed_s": elapsed,
            "sample": drive_sample(terrain, et, east, north), "sources": drive_sources(terrain)}
