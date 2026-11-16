"""Repeat the two nominal VIPER commands on the first published PGDA78 clone."""
import json
from pathlib import Path
import tempfile

import numpy as np

from backend.clavius.drive_environment import drive_sources, replay_samples
from backend.clavius.terrain import site
from scripts.prepare_drive_sunlight import EPOCHS
from scripts.record_viper_drives import OUT, ROOT, EXE, record_pair, read_frames, sha, verified_runtime

REALIZATION = "pgda78-0001"


def measurements(folder, trace):
    for entry in (trace, trace["wheels"]):
        if sha(folder/entry["file"]) != entry["sha256"]:
            raise ValueError("Recording checksum mismatch")
    frames = read_frames(folder/trace["file"])
    wheels = np.fromfile(folder/trace["wheels"]["file"], dtype="<f4").reshape(401,4,5)
    # Begin after the speed ramp. Each load row ends its preceding 50 ms window.
    displacement = frames[-1,0,:2] - frames[80,0,:2]
    return dict(displacement_en_m=displacement.tolist(), mean_load_n=wheels[81:,:,0].astype(float).mean(axis=0).tolist())


def prepare_case(identity, nominal, temp):
    terrain = site(identity, REALIZATION)
    base_grid = nominal["levels"][0]
    axis = np.arange(-1280,1281,5)
    terrain_grid = terrain.height(*np.meshgrid(axis,axis)).astype("<f4")
    grid_path = temp/f"{identity}-{REALIZATION}-drive.bin"
    terrain_grid.tofile(grid_path)
    source = terrain.manifest["realization"]["asset"]
    grid = {**base_grid,"file":grid_path.name,"sha256":sha(grid_path),
            "source":source["id"],"source_sha256":source["sha256"]}
    trace = record_pair(identity+"-"+REALIZATION,grid_path,temp)
    return dict(grid=grid, replays=trace, analysis_origin=terrain.manifest["analysis_origin"])


def main():
    replays = json.loads((OUT/"replays.json").read_text())
    if (verified_runtime()["runtime_identity"] != replays["runtime_identity"] or
            sha(EXE) != replays["executable_sha256"] or
            sha(ROOT/"scripts/viper_wheels.py") != replays["wheel_telemetry"]["reducer_sha256"]):
        raise ValueError("Use the same native recorder and wheel reducer as the nominal runs")
    nominal = json.loads((OUT/"index.json").read_text())
    study = dict(realization=REALIZATION, nominal_replays_sha256=sha(OUT/"replays.json"),
                 native_runtime=replays["runtime_identity"], analysis_interval_s=[4,20], sites={})
    with tempfile.TemporaryDirectory(dir=ROOT/"data/runtime") as folder:
        temp=Path(folder)
        for identity, info in nominal["sites"].items():
            print("Recording",identity,flush=True)
            entry = prepare_case(identity,info,temp)
            terrain = site(identity,REALIZATION)
            primary = replays["sites"][identity]
            pair = entry["replays"]
            entry["comparison"] = {}
            entry["sunlight"] = {"sources":drive_sources(terrain),"maneuvers":{}}
            for mode, base, alternative in (("straight",primary,pair),("crab",primary["maneuvers"]["crab"],pair["maneuvers"]["crab"])):
                entry["comparison"][mode] = {"nominal":measurements(OUT,base),REALIZATION:measurements(temp,alternative)}
                frames = read_frames(temp/alternative["file"])
                series = {"replay_sha256":alternative["sha256"],"samples":{
                    utc:replay_samples(terrain,utc,frames,20) for utc in EPOCHS}}
                if mode=="straight":
                    entry["sunlight"].update(series)
                else:
                    entry["sunlight"]["maneuvers"][mode]=series
            study["sites"][identity] = entry
        path=temp/"viper-terrain-comparison.json"
        path.write_text(json.dumps(study,indent=2,allow_nan=False)+"\n")
        for output in [*temp.glob("*.bin"),path]:
            output.replace(OUT/output.name)
    for name in ("manifest.json","simulation-manifest.json"):
        path=OUT.parent/name
        manifest=json.loads(path.read_text())
        manifest["rover_drive"]["sources"]["terrain_comparison"]={
            "url":"/data/drive/viper-terrain-comparison.json","sha256":sha(OUT/"viper-terrain-comparison.json")}
        path.write_text(json.dumps(manifest,indent=2)+"\n")


if __name__=="__main__":
    main()
