"""Reproduce bounded regional and curated-site NAC observed-shadow comparisons.

Uses the production Site.horizon_directions implementation without changing the
app's terrain catalogue. A regional probe has 80 m terrain everywhere; it is
never represented as one of the 5 m rover sites. See the pinned protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import rasterio
from scipy.ndimage import binary_erosion, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from clavius.geometry import directions, epoch, solar_disk_fraction, utc_from_et
from clavius.terrain import (
    DEG, R, Site, TerrainCoverageError, cached_raster, latlon_body, site as load_site,
)

RAW = ROOT / "data/raw/lroc-validation"
PROTOCOL = ROOT / "docs/validation/observed-shadow-protocol.json"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def classify(values, dark, lit):
    """-1 unknown, 0 dark, 1 ambiguous/partial, 2 lit."""
    values = np.asarray(values)
    return np.where(np.isfinite(values), np.where(values <= dark, 0, np.where(values >= lit, 2, 1)), -1)


def confusion(observed, predicted):
    observed, predicted = np.asarray(observed), np.asarray(predicted)
    assessed = (observed >= 0) & (predicted >= 0)
    matrix = [[int(np.count_nonzero(assessed & (observed == i) & (predicted == j))) for j in range(3)] for i in range(3)]
    dark = sum(matrix[0])
    lit = sum(matrix[2])
    return {
        "rows_observed_columns_predicted": ["dark", "ambiguous_or_partial", "lit"],
        "matrix": matrix,
        "assessed_samples": int(assessed.sum()),
        "observed_valid_prediction_unknown": int(np.count_nonzero((observed >= 0) & (predicted < 0))),
        "false_sunlit_count": matrix[0][2],
        "confident_observed_dark_denominator": dark,
        "false_sunlit_fraction": matrix[0][2] / dark if dark else None,
        "false_shadow_count": matrix[2][0],
        "confident_observed_lit_denominator": lit,
        "false_shadow_fraction": matrix[2][0] / lit if lit else None,
    }


def boundary(labels, valid):
    """Exclude nodata/footprint edges, including edges of the sampled grid."""
    valid = np.asarray(valid, bool)
    interior = binary_erosion(valid, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool), border_value=0)
    changed = np.zeros(valid.shape, bool)
    for axis in (0, 1):
        changed |= labels != np.roll(labels, 1, axis)
        changed |= labels != np.roll(labels, -1, axis)
    return interior & changed


def boundary_metrics(observed, predicted, valid, spacing=200):
    a, b = boundary(observed, valid), boundary(predicted, valid)
    result = {"observation_boundary_cells": int(a.sum()), "prediction_boundary_cells": int(b.sum()), "lattice_spacing_m": spacing}
    if not a.any() or not b.any():
        return {**result, "status": "inconclusive_no_eligible_boundaries", "symmetric_median_m": None, "symmetric_p95_m": None}
    a_to_b = distance_transform_edt(~b, sampling=spacing)[a]
    b_to_a = distance_transform_edt(~a, sampling=spacing)[b]
    values = np.r_[a_to_b, b_to_a]
    return {**result, "status": "recorded", "symmetric_median_m": float(np.median(values)), "symmetric_p95_m": float(np.percentile(values, 95)), "observation_to_prediction_p95_m": float(np.percentile(a_to_b, 95)), "prediction_to_observation_p95_m": float(np.percentile(b_to_a, 95))}


def inverse_polar(x, y):
    rho = np.hypot(x, y)
    return (-np.pi / 2 + 2 * np.arctan(rho / (2 * R))) / DEG, np.mod(np.arctan2(x, y) / DEG, 360)


class RegionalProbe:
    """Supply an exact geodetic observer to the unchanged production ray tracer."""
    horizon_directions = Site.horizon_directions

    def __init__(self, regional, lat, lon, height):
        self.regional = regional
        self.local = regional
        self.lat, self.lon, self.height = float(lat), float(lon), float(height)

    def sample(self, east, north):
        if east != 0 or north != 0:
            raise ValueError("The validation probe supports its exact origin only.")
        return {"lat_deg": self.lat, "lon_deg": self.lon, "elevation_m": self.height, "covered": math.isfinite(self.height)}

    def local_horizon_sample(self, x, y):
        return self.regional.sample(x, y)


def metadata(path):
    with rasterio.open(path) as d:
        return {"width": d.width, "height": d.height, "transform": list(d.transform), "crs_wkt": d.crs.to_wkt(), "numeric_crs": d.crs.to_dict(), "nodata": str(d.nodata), "tags": d.tags(), "bounds_m": list(d.bounds)}


def sample_image(path, x, y, expected_crs):
    """Containing native pixels; masking and pixel offsets retained separately."""
    with rasterio.open(path) as d:
        if d.crs.to_dict() != expected_crs:
            raise ValueError("Image and terrain numerical CRS parameters differ: " + str(path))
        if d.transform.b or d.transform.d or d.transform.a != 20 or d.transform.e != -20:
            raise ValueError("Unsupported observation grid: " + str(path))
        row = np.floor((y - d.transform.f) / d.transform.e).astype(int)
        col = np.floor((x - d.transform.c) / d.transform.a).astype(int)
        inside = (row >= 0) & (row < d.height) & (col >= 0) & (col < d.width)
        values = np.full(x.shape, np.nan)
        displacement = np.full(x.shape, np.nan)
        if inside.any():
            array = d.read(1, masked=True)
            samples = array[row[inside], col[inside]].filled(np.nan)
            values[inside] = np.where(np.isfinite(samples), samples, np.nan)
            cx = d.transform.c + (col[inside] + .5) * 20
            cy = d.transform.f - (row[inside] + .5) * 20
            displacement[inside] = np.hypot(cx - x[inside], cy - y[inside])
        return values, displacement


def camera_clock(path):
    tree = ET.parse(path)
    root = tree.getroot()
    def field(area, name):
        value = root.find("{*}" + area + "/{*}" + name)
        if value is None or not value.text:
            raise ValueError("Missing PDS4 field: " + area + "/" + name)
        return value.text
    start = field("Observation_Area/{*}Time_Coordinates", "start_date_time")
    stop = field("Observation_Area/{*}Time_Coordinates", "stop_date_time")
    a, b = epoch(start), epoch(stop)
    if b < a:
        raise ValueError("Reversed acquisition interval")
    return {"start_utc": start, "stop_utc": stop, "midpoint_utc": utc_from_et((a + b) / 2), "midpoint_et_s": (a + b) / 2, "span_si_s": b - a, "logical_identifier": field("Identification_Area", "logical_identifier"), "version_id": field("Identification_Area", "version_id")}


def enu_for_location(target, lat, lon):
    """Intersect the geocentric ray with the site's z=0 tangent plane.

    This inverts Site.location exactly; projecting the elevated surface directly
    would introduce a geographic offset away from the ENU origin.
    """
    unit = latlon_body(lat, lon, 1.)
    up = target.rotation[:, 2]
    radius = (target.origin @ up) / (unit @ up)
    return (unit * np.asarray(radius)[..., None] - target.origin) @ target.rotation


def predict_grid(label, x, y, observed, camera, clocks, provider, levels):
    lat, lon = inverse_polar(x, y)
    fraction, horizon, solar_elevation = (np.full(x.shape, np.nan) for _ in range(3))
    unknown = {"no_observer_height": 0, "ray_leaves_terrain_coverage": 0}
    valid_indices = np.flatnonzero(np.isfinite(observed))
    refinement = []
    for ordinal, k in enumerate(valid_indices):
        ij = np.unravel_index(k, x.shape)
        probe, east, north, height = provider(float(lat[ij]), float(lon[ij]), float(x[ij]), float(y[ij]))
        if not math.isfinite(height):
            unknown["no_observer_height"] += 1
            continue
        et = clocks[camera[ij]]["midpoint_et_s"]
        sun = directions(et, float(lat[ij]), float(lon[ij]), height)["sun"]
        def trace(solar, level=1):
            h = float(probe.horizon_directions(east, north, [solar["azimuth_deg"]], observer_height=0, refinement=level)[0])
            return h, solar_disk_fraction(solar["elevation_deg"], h, solar["angular_radius_deg"])
        try:
            h, f = trace(sun)
        except TerrainCoverageError:
            unknown["ray_leaves_terrain_coverage"] += 1
            continue
        fraction[ij], horizon[ij], solar_elevation[ij] = f, h, sun["elevation_deg"]
        if ordinal % 20 == 0:
            values = [{"refinement": 1, "horizon_deg": h, "visible_fraction": f}]
            for level in levels[1:]:
                refined_h, refined_f = trace(sun, level)
                values.append({"refinement": level, "horizon_deg": refined_h, "visible_fraction": refined_f})
            endpoints = []
            for endpoint in ("start_utc", "stop_utc"):
                timed = directions(epoch(clocks[camera[ij]][endpoint]), float(lat[ij]), float(lon[ij]), height)["sun"]
                try:
                    endpoints.append(trace(timed)[1])
                except TerrainCoverageError:
                    endpoints.append(None)
            refinement.append({"row": int(ij[0]), "col": int(ij[1]), "x_m": int(x[ij]), "y_m": int(y[ij]), "horizon_change_deg": abs(values[1]["horizon_deg"] - h), "visible_fraction_change": abs(values[1]["visible_fraction"] - f), "refinement_levels": values, "acquisition_endpoint_visible_fractions": endpoints, "midpoint_visible_fraction": f})
        if ordinal and ordinal % 2000 == 0:
            print(label, ordinal, "/", len(valid_indices), "samples", flush=True)
    summary = {"samples": refinement, "max_horizon_change_deg": max((a["horizon_change_deg"] for a in refinement), default=None), "max_visible_fraction_change": max((a["visible_fraction_change"] for a in refinement), default=None), "horizon_target_failures": sum(a["horizon_change_deg"] > .05 for a in refinement), "fraction_target_failures": sum(a["visible_fraction_change"] > .05 for a in refinement)}
    summary["successive_refinement"] = [{"from": low, "to": high, "max_horizon_change_deg": max((abs(a["refinement_levels"][i + 1]["horizon_deg"] - a["refinement_levels"][i]["horizon_deg"]) for a in refinement), default=None), "max_visible_fraction_change": max((abs(a["refinement_levels"][i + 1]["visible_fraction"] - a["refinement_levels"][i]["visible_fraction"]) for a in refinement), default=None)} for i, (low, high) in enumerate(zip(levels, levels[1:]))]
    return fraction, horizon, solar_elevation, unknown, summary


def observed_metrics(observed, fraction, protocol):
    predicted = classify(fraction, .05, .95)
    return [{"thresholds_if": thresholds, **confusion(classify(observed, thresholds["dark_at_most"], thresholds["lit_at_least"]), predicted)} for thresholds in [protocol["reflectance_proxy"]["primary"], *protocol["reflectance_proxy"]["sensitivity"]]]


def validate_scene(scene, regional, protocol, sources):
    scene_id = scene["id"]
    obs_paths = [RAW / scene["cameras"][c]["image_file"] for c in ("LE", "RE")]
    headers = [metadata(p) for p in obs_paths]
    west = min(h["bounds_m"][0] for h in headers)
    east = max(h["bounds_m"][2] for h in headers)
    south = min(h["bounds_m"][1] for h in headers)
    north = max(h["bounds_m"][3] for h in headers)
    xs = np.arange(math.ceil((west - 10) / 200), math.floor((east - 10) / 200) + 1) * 200 + 10
    ys = np.arange(math.floor((north - 10) / 200), math.ceil((south - 10) / 200) - 1, -1) * 200 + 10
    x, y = np.meshgrid(xs, ys)
    crs = regional.projection
    observed, displacement, camera = np.full(x.shape, np.nan), np.full(x.shape, np.nan), np.full(x.shape, -1, dtype=int)
    clocks = []
    for i, (name, path) in enumerate(zip(("LE", "RE"), obs_paths)):
        value, offset = sample_image(path, x, y, crs)
        keep = ~np.isfinite(observed) & np.isfinite(value) & (value <= 1)
        observed[keep], displacement[keep], camera[keep] = value[keep], offset[keep], i
        clock = camera_clock(RAW / scene["cameras"][name]["label_file"])
        if not clock["logical_identifier"].endswith("nac." + (scene_id + name).lower()):
            raise ValueError("PDS label does not identify the selected camera")
        clocks.append(clock)
    started = time.monotonic()
    levels = protocol.get("followup_refinement_levels", [1, 2])
    def regional_provider(lat, lon, px, py):
        height = float(regional.sample(px, py))
        return RegionalProbe(regional, lat, lon, height), 0, 0, height
    fraction, horizon, solar_elevation, unknown, refinement = predict_grid(scene_id, x, y, observed, camera, clocks, regional_provider, levels)
    predicted_class = classify(fraction, .05, .95)
    comparisons = observed_metrics(observed, fraction, protocol)
    both = np.isfinite(observed) & np.isfinite(fraction)
    model, _ = sample_image(RAW / scene["model_file"], x, y, crs)
    model_comparison = confusion(np.where(np.isfinite(model) & np.isfinite(observed), np.where(model > 0, 2, 0), -1), predicted_class)
    local_overlap = []
    local_comparisons = []
    local_arrays = {}
    for entry in sources["sites"]:
        asset = next(a for a in sources["terrain"]["assets"] if a["id"] == entry["local_asset_id"])
        with rasterio.open(ROOT / "data/raw" / asset["file"]) as d:
            b = d.bounds
            within = (x > b.left + 10) & (x < b.right - 10) & (y > b.bottom + 10) & (y < b.top - 10) & np.isfinite(observed)
        local_overlap.append({"site_id": entry["id"], "observed_lattice_samples_in_local_domain": int(within.sum()), "status": "no_overlap" if not within.any() else "local_comparison_recorded"})
        if not within.any():
            continue
        target = load_site(entry["id"])
        local_observed = np.where(within, observed, np.nan)
        def local_provider(lat, lon, px, py):
            east, north = enu_for_location(target, lat, lon)[:2]
            point = target.sample(east, north)
            return target, float(east), float(north), float(point["elevation_m"])
        lf, lh, le, lu, lr = predict_grid(scene_id + "/" + entry["id"], x, y, local_observed, camera, clocks, local_provider, levels)
        covered = within & np.isfinite(lf)
        local_comparisons.append({"site_id": entry["id"], "scope": "production_5m_local_plus_80m_regional_nominal_terrain", "observer_height_m": 0, "single_observed_epoch_only": True, "source_manifest": target.manifest, "observed_samples": int(within.sum()), "assessed_samples": int(covered.sum()), "unknown_counts": lu, "observed_proxy_comparisons": observed_metrics(local_observed, lf, protocol), "boundaries": boundary_metrics(observed >= .003, lf >= .5, covered), "refinement": lr})
        for name, value in [("visible_fraction", lf), ("horizon_deg", lh), ("solar_elevation_deg", le), ("domain_mask", within)]:
            local_arrays[entry["id"] + "_" + name] = value
    report = {
        "scene_id": scene_id, "scope": "regional_80m_only_not_curated_5m_rover_sites",
        "status": "comparison_recorded" if both.any() else "unassessed_no_complete_ray_coverage",
        "cameras": dict(zip(("LE", "RE"), clocks)),
        "grid": {"shape": list(x.shape), "spacing_m": 200, "west_center_m": int(xs[0]), "north_center_m": int(ys[0]), "camera_priority": "LE then RE", "observed_samples": int(np.isfinite(observed).sum()), "assessed_samples": int(both.sum()), "max_observation_pixel_center_displacement_m": float(np.nanmax(displacement[np.isfinite(observed)]))},
        "unknown_counts": unknown, "curated_site_overlap": local_overlap, "local_site_comparisons": local_comparisons,
        "observed_proxy_comparisons": comparisons,
        "boundaries": boundary_metrics(observed >= .003, fraction >= .5, both),
        "nasa_rendering_reference": {"quantity": "W/m2, positive vs zero; no raw-brightness comparison with NAC I/F", "comparison": model_comparison, "independent_observation": False},
        "refinement": refinement,
        "elapsed_s": round(time.monotonic() - started, 3),
    }
    arrays = {"observed_if": observed, "nasa_model_w_m2": model, "clavius_visible_fraction": fraction, "horizon_deg": horizon, "solar_elevation_deg": solar_elevation, "camera_index": camera, "observation_center_displacement_m": displacement, "x_centers_m": xs, "y_centers_m": ys, **local_arrays}
    return report, arrays


def verify_assets(spec, fetch=False):
    RAW.mkdir(parents=True, exist_ok=True)
    for a in spec["assets"]:
        path = RAW / a["file"]
        if not path.is_file() or digest(path) != a["sha256"]:
            if not fetch:
                raise ValueError("Missing or altered source; rerun with --fetch: " + a["file"])
            if shutil.disk_usage(RAW).free - a["bytes"] < 256 * 1024 ** 2:
                raise ValueError("Preserving 256 MiB free; insufficient space for " + a["file"])
            temp = path.with_suffix(path.suffix + ".part")
            with urlopen(a["url"], timeout=60) as source, temp.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if temp.stat().st_size != a["bytes"] or digest(temp) != a["sha256"]:
                raise ValueError("Downloaded source identity mismatch: " + a["file"])
            temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/validation/observed-shadow-comparison.json")
    args = parser.parse_args()
    sources = json.loads((ROOT / "public/data/simulation-manifest.json").read_text())
    spec = sources["observed_shadow_validation"]
    verify_assets(spec, args.fetch)
    protocol = json.loads(PROTOCOL.read_text())
    if digest(PROTOCOL) != spec["protocol_sha256"]:
        raise ValueError("Protocol differs from the pinned source manifest")
    for record in spec["catalogue_archives"]:
        if digest(ROOT / record["file"]) != record["sha256"]:
            raise ValueError("Archived catalogue response differs")
    if digest(ROOT / spec["coverage_preflight_file"]) != spec["coverage_preflight_sha256"]:
        raise ValueError("Coverage selection record differs")
    regional_asset = next(a for a in sources["terrain"]["assets"] if a["id"] == sources["sites"][0]["regional_asset_id"])
    path = ROOT / "data/raw" / regional_asset["file"]
    if digest(path) != regional_asset["sha256"]:
        raise ValueError("Regional source hash mismatch")
    regional = cached_raster(regional_asset["file"], regional_asset["sha256"])
    results = []
    derivatives = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for scene in spec["scenes"]:
        report, arrays = validate_scene(scene, regional, protocol, sources)
        output = args.output.parent / (scene["id"] + "-shadow-samples.npz")
        np.savez_compressed(output, **arrays)
        derivatives.append({"file": output.name, "bytes": output.stat().st_size, "sha256": digest(output)})
        results.append(report)
        print(scene["id"], report["status"], report["grid"], flush=True)
    import scipy, spiceypy
    report = {
        "model_id": protocol["version"], "protocol": protocol, "protocol_sha256": digest(PROTOCOL),
        "source_manifest_section": spec, "regional_terrain": regional_asset,
        "kernel_assets": sources["kernels"]["assets"],
        "implementation_sha256": {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__).resolve(), ROOT / "backend/clavius/terrain.py", ROOT / "backend/clavius/geometry.py"]},
        "software": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__, "rasterio": rasterio.__version__, "spiceypy": spiceypy.__version__},
        "scenes": results, "sample_derivatives": derivatives,
        "limitations": ["Observed reflectance thresholds are proxies, not independently annotated shadow truth.", "Two regional dates; the curated 5 m sites overlap only one observed epoch, separately recorded.", "No registration fitting; nearest image pixel is up to 14.15 m from a common 200 m lattice point.", "Midpoint exposure times approximate a pushbroom image; sampled endpoint sensitivity is recorded.", "The solar-disk model uses a locally straight horizon at center azimuth; no scattering or limb darkening.", "Incomplete terrain rays remain unknown; unknown samples never improve agreement denominators.", "Neither this sample nor the threshold sensitivity establishes an operational error bound."],
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Recorded", args.output)


if __name__ == "__main__":
    main()
