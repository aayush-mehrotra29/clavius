"""Capture or replay the independent lunar geometry comparison with JPL Horizons."""
import argparse
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import numpy as np

from backend.clavius.drive_environment import drive_sources
from backend.clavius.geometry import directions, epoch
from backend.clavius.terrain import site

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/"docs/validation/horizons-geometry"
REPORT = ROOT/"public/data/horizons-geometry.json"
API = "https://ssd.jpl.nasa.gov/api/horizons.api"
BODIES = {"moon":301, "sun":10, "earth":399}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def stations(protocol):
    stations = {"north-pole":(0.,0.,protocol["sphere_radius_km"])}
    for name in protocol["sites"]:
        terrain=site(name)
        altitude=float(terrain.sample(0,0)["elevation_m"])+protocol["observer_height_m"]
        radius=protocol["sphere_radius_km"]+altitude/1000
        lat=np.radians(terrain.lat)
        stations[name]=(terrain.lon%360,radius*np.cos(lat),radius*np.sin(lat))
    return stations


def requests_for(protocol):
    for station, coords in stations(protocol).items():
        for body, target in BODIES.items():
            if station=="north-pole" and body!="moon":
                continue
            params=dict(COMMAND=str(target),CENTER="coord@301",COORD_TYPE="CYLINDRICAL",
                        SITE_COORD=",".join(f"{v:.12f}" for v in coords),
                        EPHEM_TYPE="VECTORS",REF_SYSTEM="ICRF",REF_PLANE="FRAME",VEC_CORR="NONE",
                        VEC_TABLE="1",OUT_UNITS="KM-S",TIME_TYPE="UT",CSV_FORMAT="YES",
                        TLIST_TYPE="CAL",OBJ_DATA="NO")
            query={k:"'"+v+"'" for k,v in params.items()}
            query["TLIST"]=",".join("'"+t[:-1].replace("T"," ")+"'" for t in protocol["epochs_utc"])
            yield station,body,coords,API+"?"+urlencode({"format":"json",**query})


def parse_reply(raw,body,coords,epochs):
    data=json.loads(raw)
    if data.get("error"):
        raise ValueError(data["error"])
    result=data["result"]
    header, rest=result.split("$$SOE",1)
    expected = {
        "Target body name":rf"{body}\s+\({BODIES[body]}\)\s+\{{source: DE441\}}",
        "Center body name":r"Moon\s+\(301\)\s+\{source: DE441\}",
        "Center pole/equ":r"MEAN_ME \(high precision\)\s+\{East-longitude positive\}",
        "Reference frame":"ICRF","Output units":"KM-S","Output type":"GEOMETRIC cartesian states",
    }
    for key, pattern in expected.items():
        if not re.search("^"+key+r"\s*:\s*"+pattern+r"\s*$",header,re.M|re.I):
            raise ValueError("Unexpected Horizons convention: "+key)
    if "Calendar Date (UT" not in header or "JDUT" not in header:
        raise ValueError("Missing UT calendar columns")
    printed=re.search(r"^Center cylindric:\s*([^{}]+?)\s*\{E-lon\(deg\),Dxy\(km\),Dz\(km\)\}",header,re.M)
    if not printed:
        raise ValueError("Missing observer coordinates")
    # Horizons rounds to fit the header line, using a different number of
    # decimal places at each site. The full vectors supply the radius/lat checks.
    fields=[Decimal(v.strip()) for v in printed[1].split(",")]
    rounding=[.5*10**v.as_tuple().exponent+1e-12 for v in fields]
    if not np.allclose([float(v) for v in fields],coords,atol=rounding,rtol=0):
        raise ValueError("Different observer coordinates in response")
    table=rest.split("$$EOE")[0]
    if "$$EOE" not in rest:
        raise ValueError("Incomplete vector table")
    values=[]
    for row in csv.reader(table.strip().splitlines(),skipinitialspace=True):
        if len(row)!=6 or row[-1].strip():
            raise ValueError("Unexpected Horizons vector columns")
        time=datetime.strptime(row[1].strip(),"A.D. %Y-%b-%d %H:%M:%S.%f")
        values.append((time,[float(v) for v in row[2:5]]))
    times=[datetime.fromisoformat(t[:-1]) for t in epochs]
    if [v[0] for v in values]!=times:
        raise ValueError("Different or incomplete Horizons epochs")
    vectors=np.array([v[1] for v in values])
    if not np.isfinite(vectors).all():
        raise ValueError("Nonfinite reference")
    return vectors


def capture(protocol):
    index=ARCHIVE/"requests.json"
    if index.exists():
        raise ValueError("A pinned observation set already exists. Use offline replay.")
    records={}
    for station,body,coords,url in requests_for(protocol):
        path=ARCHIVE/f"{station}-{body}.json"
        with urlopen(url,timeout=90) as res:
            raw=res.read()
        parse_reply(raw,body,coords,protocol["epochs_utc"])
        path.write_bytes(raw)
        records[path.name]={"url":url,"sha256":sha(path)}
        print("Captured",path.name,flush=True)
    write(index,records)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--capture",action="store_true")
    parser.add_argument("--publish",action="store_true")
    args=parser.parse_args()
    protocol=read(ARCHIVE/"protocol.json")
    if args.capture:
        capture(protocol)
    result=compare(protocol)
    if args.publish:
        publish(result)
    else:
        for name in ("manifest.json","simulation-manifest.json"):
            pin=read(REPORT.parent/name)["horizons_geometry"]
            if pin["sha256"]!=sha(REPORT) or pin["url"]!="/data/"+REPORT.name:
                raise ValueError("Published comparison identity mismatch")
        verify_reproduction(read(REPORT),result)
    print(result["passed"],result["max_errors"],flush=True)
    if not result["passed"]:
        raise SystemExit(1)


def unit(vector):
    return vector/np.linalg.norm(vector)


def separation(a,b):
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a,b)),np.dot(a,b))))


def reference_axes(to_moon,pole_to_moon):
    up=unit(-to_moon)
    pole=unit(-pole_to_moon)
    east=unit(np.cross(pole,up))
    return np.column_stack((east,np.cross(up,east),up))


def same_request(recorded,current):
    # Cylindrical coordinates can differ in the final decimal place across
    # libc/projection implementations. Permit 1e-9 km in each distance.
    old,new=urlsplit(recorded),urlsplit(current)
    if old._replace(query="")!=new._replace(query=""):
        return False
    a,b=parse_qs(old.query),parse_qs(new.query)
    def station(params):
        return [float(v) for v in params.pop("SITE_COORD")[0].strip("'").split(",")]
    return np.allclose(station(a),station(b),rtol=0,atol=1e-9) and a==b


def verify_reproduction(expected,actual):
    if isinstance(expected,dict):
        if expected.keys()!=actual.keys():
            raise ValueError("Different comparison fields")
        for k in expected:
            verify_reproduction(expected[k],actual[k])
    elif isinstance(expected,list):
        if len(expected)!=len(actual):
            raise ValueError("Different comparison count")
        for a,b in zip(expected,actual):
            verify_reproduction(a,b)
    elif isinstance(expected,float):
        if not np.isclose(expected,actual,rtol=1e-14,atol=1e-8):
            raise ValueError(f"Numerical reproduction mismatch: {expected}, {actual}")
    elif expected!=actual:
        raise ValueError("Different comparison identities or outcomes")


def compare(protocol):
    epochs=protocol["epochs_utc"]
    records=read(ARCHIVE/"requests.json")
    vectors={}
    for station,body,coords,url in requests_for(protocol):
        path=ARCHIVE/f"{station}-{body}.json"
        pin=records[path.name]
        if not same_request(pin["url"],url) or sha(path)!=pin["sha256"]:
            raise ValueError("Horizons request or response identity mismatch: "+path.name)
        vectors[station,body]=parse_reply(path.read_bytes(),body,coords,epochs)
    rows=[]
    checks={}
    limits=protocol["gates"]
    for name in protocol["sites"]:
        terrain=site(name)
        point=terrain.sample(0,0)
        lat,lon=float(point["lat_deg"]),float(point["lon_deg"])
        altitude=float(point["elevation_m"])+protocol["observer_height_m"]
        radius=protocol["sphere_radius_km"]+altitude/1000
        station_checks={"radius_m":0., "latitude_deg":0., "sun_clock_shift_deg":0., "earth_no_parallax_deg":0.}
        for i,utc in enumerate(epochs):
            moon=vectors[name,"moon"][i]
            pole=vectors["north-pole","moon"][i]
            axes=reference_axes(moon,pole)
            measured_lat=np.degrees(np.arcsin(np.dot(axes[:,2],unit(-pole))))
            station_checks["radius_m"]=max(station_checks["radius_m"],abs(np.linalg.norm(moon)-radius)*1000)
            station_checks["latitude_deg"]=max(station_checks["latitude_deg"],abs(measured_lat-lat))
            et=epoch(utc)
            model=directions(et,lat,lon,altitude)
            for body in ("sun","earth"):
                ray=vectors[name,body][i]
                enu=unit(ray)@axes
                expected=dict(azimuth_deg=float(np.degrees(np.arctan2(enu[0],enu[1]))%360),
                              elevation_deg=float(np.degrees(np.arctan2(enu[2],np.hypot(*enu[:2])))),
                              distance_km=float(np.linalg.norm(ray)))
                computed={key:model[body][key] for key in expected}
                error=dict(direction_deg=separation(enu,model[body]["enu"]),
                           azimuth_deg=abs((computed["azimuth_deg"]-expected["azimuth_deg"]+180)%360-180),
                           elevation_deg=abs(computed["elevation_deg"]-expected["elevation_deg"]),
                           range_km=abs(computed["distance_km"]-expected["distance_km"]))
                passed=all(error[key]<=limits[key] for key in ("direction_deg","azimuth_deg","elevation_deg"))
                rows.append(dict(site=name,utc=utc,target=body,clavius=computed,horizons=expected,errors=error,
                                 passed=passed and error["range_km"]<=limits["range_km"][body]))
                if body=="sun":
                    shifted=directions(et+3600,lat,lon,altitude)["sun"]["enu"]
                    station_checks["sun_clock_shift_deg"]=max(station_checks["sun_clock_shift_deg"],separation(enu,shifted))
                else:
                    center_direction=unit(ray-moon)@axes
                    station_checks["earth_no_parallax_deg"]=max(station_checks["earth_no_parallax_deg"],separation(enu,center_direction))
        station_checks["passed"]=bool(station_checks["radius_m"]<=limits["station_radius_error_m"] and
            station_checks["latitude_deg"]<=limits["latitude_error_deg"] and
            min(station_checks["sun_clock_shift_deg"],station_checks["earth_no_parallax_deg"])>limits["minimum_negative_control_deg"])
        checks[name]={"latitude_deg":lat,"longitude_east_deg":lon,"altitude_above_sphere_m":altitude,
                      "sources":drive_sources(terrain),"checks":station_checks}
    maxima={body:{key:max(row["errors"][key] for row in rows if row["target"]==body)
                  for key in rows[0]["errors"]} for body in ("sun","earth")}
    return dict(model="clavius-horizons-geometry-v1",role="validation only",ephemerides={"clavius":"DE421","horizons":"DE441"},
                protocol_sha256=sha(ARCHIVE/"protocol.json"),requests_sha256=sha(ARCHIVE/"requests.json"),
                records=records,criteria=limits,sites=checks,rows=rows,max_errors=maxima,
                passed=all(r["passed"] for r in rows) and all(r["checks"]["passed"] for r in checks.values()))


def publish(result):
    write(REPORT,result)
    source={"url":"/data/"+REPORT.name,"sha256":sha(REPORT),"role":"External geometric direction and range comparison at two nominal site origins."}
    for name in ("manifest.json","simulation-manifest.json"):
        path=REPORT.parent/name
        m=read(path)
        m["horizons_geometry"]=source
        write(path,m)


if __name__=="__main__":
    main()
