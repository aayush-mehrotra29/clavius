"""Scientific validation guards: missing support cannot become apparent agreement."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("observed_shadows", Path(__file__).resolve().parents[1] / "scripts/validate_observed_shadows.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unknown_predictions_do_not_enter_accuracy_denominators():
    result = module.confusion([0, 0, 2, 2, 1], [-1, 2, 0, 1, 2])
    assert result["observed_valid_prediction_unknown"] == 1
    assert result["confident_observed_dark_denominator"] == 1
    assert result["false_sunlit_fraction"] == 1
    assert result["false_shadow_fraction"] == .5
    assert module.confusion([0, 2], [-1, -1])["false_sunlit_fraction"] is None


def test_reflectance_proxy_preserves_ambiguity_and_negative_calibrated_values():
    assert module.classify(np.array([np.nan, -.0001, .001, .003, .005]), .001, .005).tolist() == [-1, 0, 0, 1, 2]


def test_footprint_and_nodata_edges_are_not_shadow_boundaries():
    labels = np.zeros((7, 7), bool)
    labels[:, 3:] = True
    valid = np.ones_like(labels)
    valid[:, 2:4] = False
    assert not module.boundary(labels, valid).any()
    assert module.boundary_metrics(labels, labels, valid)["symmetric_p95_m"] is None


def test_boundary_distance_has_physical_units_and_excludes_outer_edges():
    a, b = np.zeros((9, 9), bool), np.zeros((9, 9), bool)
    a[:, 3:] = True
    b[:, 5:] = True
    result = module.boundary_metrics(a, b, np.ones_like(a), spacing=200)
    assert result["symmetric_p95_m"] == 400
    assert result["symmetric_median_m"] == 300


def test_image_sampling_respects_native_mask_and_subpixel_grid_origin(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    crs = {"proj": "stere", "lat_0": -90, "lat_ts": -90, "lon_0": 0, "R": 1737400, "units": "m"}
    path = tmp_path / "image.tif"
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32", transform=from_origin(.85, 40.13, 20, 20), crs=crs, nodata=-9999) as d:
        d.write(np.array([[.01, -9999], [.002, .003]], dtype="float32"), 1)
    with rasterio.open(path) as d:
        expected = d.crs.to_dict()
    values, displacement = module.sample_image(path, np.array([10., 30., 100.]), np.array([30., 30., 100.]), expected)
    assert np.isclose(values[0], .01)
    assert np.isnan(values[1:]).all()
    assert np.isclose(displacement[0], np.hypot(.85, .13))


def test_south_polar_inverse_round_trip():
    from clavius.terrain import stereographic
    lat, lon = np.array([-89.8, -85.5, -81.4]), np.array([204.04, 21.2, 276.8])
    x, y = stereographic(lat, lon)
    actual_lat, actual_lon = module.inverse_polar(x, y)
    assert np.max(np.abs(actual_lat - lat)) < 1e-10
    assert np.max(np.abs(actual_lon - lon)) < 1e-10


def test_label_identity_uses_identification_area_not_modification_history(tmp_path, monkeypatch):
    path = tmp_path / "label.xml"
    path.write_text('''<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
      <Identification_Area><logical_identifier>urn:example:nac.testle</logical_identifier><version_id>2.0</version_id>
        <Modification_History><Modification_Detail><version_id>1.0</version_id></Modification_Detail></Modification_History>
      </Identification_Area>
      <Observation_Area><Time_Coordinates><start_date_time>start</start_date_time><stop_date_time>stop</stop_date_time></Time_Coordinates></Observation_Area>
    </Product_Observational>''')
    monkeypatch.setattr(module, "epoch", lambda value: {"start": 10., "stop": 30.}[value])
    monkeypatch.setattr(module, "utc_from_et", lambda value: "midpoint")
    clock = module.camera_clock(path)
    assert clock["version_id"] == "2.0"
    assert clock["span_si_s"] == 20
    assert clock["midpoint_et_s"] == 20


def test_validation_locations_round_trip_through_production_enu_frame():
    from types import SimpleNamespace
    from clavius.terrain import basis, latlon_body, Site, R
    target = SimpleNamespace(origin=latlon_body(-89.44, 222.8, R + 1800), rotation=basis(-89.44, 222.8))
    for lat, lon in [(-89.44, 222.8), (-89.3, 210), (-89.6, 235)]:
        east, north, up = module.enu_for_location(target, lat, lon)
        actual_lat, actual_lon = Site.location(target, east, north)
        assert abs(up) < 1e-8
        assert abs(actual_lat - lat) < 1e-10
        assert abs((actual_lon - lon + 180) % 360 - 180) < 1e-10
