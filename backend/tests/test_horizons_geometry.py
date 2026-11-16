from pathlib import Path
import json

import numpy as np
import pytest
from scripts.validate_horizons_geometry import (
    ARCHIVE, REPORT, compare, parse_reply, read, reference_axes, requests_for, sha, verify_reproduction
)


def test_external_reference_reproduces_all_sites_targets_and_epochs_offline():
    protocol=read(ARCHIVE/"protocol.json")
    result=compare(protocol)
    verify_reproduction(read(REPORT),result)
    assert {(r["site"],r["target"],r["utc"]) for r in result["rows"]} == {
        (s,b,utc) for s in protocol["sites"] for b in ("sun","earth") for utc in protocol["epochs_utc"]}
    assert all(r["passed"] for r in result["rows"]) and result["passed"]
    for station in result["sites"].values():
        checks=station["checks"]
        assert checks["passed"] and min(checks["sun_clock_shift_deg"], checks["earth_no_parallax_deg"]) > .05
    for name in ("manifest.json","simulation-manifest.json"):
        assert read(REPORT.parent/name)["horizons_geometry"]["sha256"]==sha(REPORT)


@pytest.mark.parametrize("old,new",[
    ("GEOMETRIC cartesian states","LT CORRECTED cartesian states"),("Reference frame : ICRF","Reference frame : Ecliptic"),
    ("2028-Jan-21 12:00:00.0000,","2028-Jan-21 12:01:00.0000,"),("DE441","DE430"),
    ("$$EOE",""),("Center cylindric: 222.8","Center cylindric: 220.8")
])
def test_rejects_different_direction_time_or_station_conventions(old,new):
    protocol=read(ARCHIVE/"protocol.json")
    station,body,coords,_=next(r for r in requests_for(protocol) if r[:2]==("connecting-ridge","earth"))
    record=read(ARCHIVE/f"{station}-{body}.json")
    assert old in record["result"]
    record["result"]=record["result"].replace(old,new)
    with pytest.raises((ValueError,IndexError)):
        parse_reply(json.dumps(record),body,coords,protocol["epochs_utc"])


def test_external_basis_points_east_north_up_from_two_reference_vectors():
    # On the meridian, the surface point is at +X and the north pole at +Z.
    axes=reference_axes(np.array([-2.,0,0]),np.array([0,0,-3.]))
    np.testing.assert_allclose(np.eye(3)@axes,[[0,0,1],[1,0,0],[0,1,0]])
