"""Check the packaged drive comparison against native pose, wheel and science inputs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from clavius.api import app
from clavius.terrain import site
from clavius.drive_environment import live_sample

DATA = Path(__file__).resolve().parents[2]/"public/data"
DRIVE = DATA/"drive"
CLONE = "pgda78-0001"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


@pytest.mark.parametrize("identity", ["connecting-ridge","shackleton-rim"])
def test_clone_geometry_contact_and_horizon_share_one_surface(identity):
    catalog = load(DRIVE/"viper-terrain-comparison.json")
    row = catalog["sites"][identity]
    original = load(DRIVE/"replays.json")
    nominal = original["sites"][identity]
    terrain, base_terrain = site(identity,CLONE), site(identity)
    np.testing.assert_array_equal(terrain.origin,base_terrain.origin)
    assert catalog["nominal_replays_sha256"] == digest(DRIVE/"replays.json")
    for manifest in ["manifest.json","simulation-manifest.json"]:
        assert load(DATA/manifest)["rover_drive"]["sources"]["terrain_comparison"]["sha256"] == digest(DRIVE/"viper-terrain-comparison.json")
    grid = row["grid"]
    assert grid["source_sha256"] == terrain.manifest["realization"]["asset"]["sha256"]
    assert grid["sha256"] == digest(DRIVE/grid["file"])
    raster = np.fromfile(DRIVE/grid["file"],"<f4").reshape(513,513)
    i,j=np.meshgrid(np.array([0,128,255,256,257,512]),np.array([1,234,256,387,511]))
    np.testing.assert_array_equal(raster[j,i],terrain.height((i-256)*5,(j-256)*5).astype("<f4"))
    assert raster[256,256] != 0
    for mode in ["straight","crab"]:
        clone_trace = row["replays"]
        base_trace = nominal
        light = row["sunlight"]
        if mode=="crab":
            clone_trace,base_trace,light=(entry["maneuvers"]["crab"] for entry in [clone_trace,base_trace,light])
        assert clone_trace["terrain_sha256"] == grid["sha256"] != base_trace["terrain_sha256"]
        for variant, trace in [("nominal",base_trace),(CLONE,clone_trace)]:
            stats=row["comparison"][mode][variant]
            assert digest(DRIVE/trace["file"])==trace["sha256"]==trace["wheels"]["pose_sha256"]
            assert digest(DRIVE/trace["wheels"]["file"])==trace["wheels"]["sha256"]
            frames=np.fromfile(DRIVE/trace["file"],"<f4").reshape(401,17,7)
            wheels=np.fromfile(DRIVE/trace["wheels"]["file"],"<f4").reshape(401,4,5)
            np.testing.assert_allclose(stats["displacement_en_m"],frames[-1,0,:2]-frames[80,0,:2],rtol=0,atol=1e-7)
            np.testing.assert_allclose(stats["mean_load_n"],wheels[81:,:,0].mean(axis=0,dtype=float),rtol=0,atol=1e-7)
        assert light["replay_sha256"]==clone_trace["sha256"]
        for epoch,rows in light["samples"].items():
            for second in [0,11,20]:
                e,n = frames[second*20,0,:2]
                actual=live_sample(identity,epoch,second,float(e),float(n),CLONE)
                assert row["sunlight"]["sources"] == actual["sources"]
                assert rows[second]["east_m"]==e and rows[second]["north_m"]==n
                for channel in ["sun_horizon_deg","earth_horizon_deg","disk_fraction"]:
                    assert rows[second][channel]==pytest.approx(actual["sample"][channel],abs=1e-8)


def test_clone_custom_requests_bind_trace_and_parking_to_selected_realization():
    api=TestClient(app)
    name="shackleton-rim"
    root=f"/api/v1/sites/{name}"
    study=load(DRIVE/"viper-terrain-comparison.json")["sites"][name]
    nominal=load(DRIVE/"replays.json")["sites"][name]
    start="2028-01-22T18:04:00Z"
    params=dict(start_utc=start,realization=CLONE,replay_sha256=study["replays"]["sha256"])
    clone=api.get(root+"/drive-replay-environment",params=params)
    assert clone.status_code==200 and clone.json()["sources"]["realization"]==CLONE
    for wrong in [dict(realization="nominal"),dict(replay_sha256=nominal["sha256"])]:
        assert api.get(root+"/drive-replay-environment",params={**params,**wrong}).status_code==422
    params=dict(start_utc=start,realization=CLONE,east_m=.4,north_m=.9)
    parked=api.get(root+"/parked-sunlight",params={**params,"hours":1}).json()
    point=api.get(root+"/drive-environment",params=params).json()
    assert parked["sources"]==point["sources"]==study["sunlight"]["sources"]
    assert parked["rows"][0][-1]==point["sample"]["disk_fraction"]
