import json
from pathlib import Path
import numpy as np
import pytest
import spiceypy as spice
from fastapi.testclient import TestClient
from clavius.api import app
from clavius.drive_environment import live_sample, start_epoch
from clavius.terrain import R, basis, latlon_body, site

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)
route = "/api/v1/sites/connecting-ridge/drive-environment"
utc = "2028-01-21T12:00:00Z"


def test_fixed_site_light_direction_matches_spkcpo_observer_state():
    # Large cross-site displacement deliberately makes local geographic north
    # and site north different. Compare with CSPICE's offset-observer routine.
    terrain = site("shackleton-rim")
    point = terrain.sample(950,-730)
    lat,lon = point["lat_deg"],point["lon_deg"]
    result = live_sample(terrain.id, utc, 3.75, 950,-730)["sample"]
    observer = latlon_body(lat, lon, R+point["elevation_m"]+.5)/1000
    state,_ = spice.spkcpo("SUN",start_epoch(utc)+3.75,"MOON_ME_DE421","OBSERVER",
                            "NONE",observer,"MOON","MOON_ME_DE421")
    unit=state[:3]/np.linalg.norm(state[:3])
    np.testing.assert_allclose(result["sun_site_enu"],unit@terrain.rotation,atol=1e-12,rtol=0)
    assert np.linalg.norm(unit@basis(lat,lon)-result["sun_site_enu"])>.02


@pytest.mark.parametrize("name",["connecting-ridge","shackleton-rim"])
@pytest.mark.parametrize("maneuver",["straight","crab"])
def test_packaged_samples_reproduce_at_recorded_pose_and_clock(name,maneuver):
    catalog = json.loads((ROOT/"public/data/drive/sunlight.json").read_text())
    replays = json.loads((ROOT/"public/data/drive/replays.json").read_text())
    trace=replays["sites"][name]
    site_catalog=catalog["sites"][name]
    samples=site_catalog
    if maneuver=="crab":
        trace=trace["maneuvers"]["crab"]
        samples=site_catalog["maneuvers"]["crab"]
    assert samples["replay_sha256"]==trace["sha256"]
    poses = np.fromfile(ROOT/"public/data/drive"/trace["file"],dtype="<f4").reshape(401,17,7)
    for start in catalog["epochs"]:
        rows = samples["samples"][start]
        assert len(rows)==21
        for t in (0,12,20):
            e,n=map(float,poses[t*20,0,:2])
            live=live_sample(name,start,t,e,n)
            assert live["sources"]==catalog["sites"][name]["sources"]
            assert live["sample"]["utc"]==rows[t]["utc"]
            assert rows[t]["east_m"]==e and rows[t]["north_m"]==n
            for key in ("sun_site_enu","disk_fraction","sun_horizon_deg","earth_horizon_deg"):
                np.testing.assert_allclose(live["sample"][key],rows[t][key],rtol=0,atol=1e-8)
    fraction=samples["samples"][utc][0]["disk_fraction"]
    assert fraction==0 if name=="connecting-ridge" else .50<fraction<.55


def test_elapsed_si_clock_resolves_positive_utc_leap_second():
    params={"start_utc":"2017-01-01T00:59:59+01:00","elapsed_s":1}
    result = client.get(route,params=params)
    assert result.status_code==200
    assert result.json()["sample"]["utc"]=="2016-12-31T23:59:60.000Z"


@pytest.mark.parametrize("values",[
    {"start_utc":"2049-12-31T23:59:59Z","elapsed_s":1},
    {"start_utc":"2050-01-01T00:30:00-05:00"},{"start_utc":"2028-01-01"},
    {"east_m":"NaN"},{"north_m":1e7},{"elapsed_s":-1}
])
def test_unsupported_samples_are_explicit(values):
    response=client.get(route,params={"start_utc":utc,**values})
    assert response.status_code==422
