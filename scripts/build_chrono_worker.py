"""Build and inventory the pinned native CPU Chrono reference worker.

Requires the source checkout and the private CMake/Eigen build environment.
Does not change upstream source, run arbitrary mission scripts, or replace the
MuJoCo/Gazebo workers. Build artifacts stay in ignored data/runtime directories.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/raw/robots/chrono'
BUILD=ROOT/'data/runtime/chrono-build'
DEPS=ROOT/'data/runtime/chrono-deps'
ADAPTER=ROOT/'data/runtime/chrono-worker-build'
COMMIT='2617649bf687456328a122b63dc0bb64df91394a'


def sha(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        while chunk:=stream.read(1024*1024): h.update(chunk)
    return h.hexdigest()


def build(skip_core=False):
    if platform.system()!='Darwin' or platform.machine()!='arm64':
        raise ValueError('This build configuration is verified for Apple Silicon macOS')
    commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    modified=subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
    if commit!=COMMIT or modified:
        raise ValueError('Chrono upstream checkout differs from the pinned original')
    cmake=str(DEPS/'bin/cmake')
    configuration=[cmake,'-S',str(SOURCE),'-B',str(BUILD),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+str(ROOT/'data/runtime/chrono-sdk'),'-DCMAKE_PREFIX_PATH='+str(DEPS),'-DENABLE_MODULE_VEHICLE=ON','-DENABLE_MODULE_VEHICLE_MODELS=OFF','-DENABLE_MODULE_VEHICLE_COSIM=OFF','-DENABLE_OPENMP=OFF','-DENABLE_TBB=OFF','-DBUILD_DEMOS=OFF','-DBUILD_TESTING=OFF','-DBUILD_BENCHMARKING=OFF','-DCMAKE_C_COMPILER=/usr/bin/clang','-DCMAKE_CXX_COMPILER=/usr/bin/clang++']
    if not skip_core:
        subprocess.run(configuration,check=True)
        subprocess.run([cmake,'--build',str(BUILD),'--parallel','2'],check=True)
    subprocess.run([cmake,'-S',str(ROOT/'workers/chrono'),'-B',str(ADAPTER),'-DChrono_DIR='+str(BUILD/'cmake'),'-DCMAKE_BUILD_TYPE=Release'],check=True)
    subprocess.run([cmake,'--build',str(ADAPTER),'--parallel','2'],check=True)
    executable=ADAPTER/'clavius_chrono_reference'
    libraries=sorted(BUILD.rglob('*.dylib'))
    if not libraries or not executable.is_file():
        raise ValueError('Native Chrono build did not produce the required runtime')
    paths=[executable,*[file for file in libraries if not file.is_symlink()],ROOT/'workers/chrono/reference.cpp',ROOT/'workers/chrono/CMakeLists.txt',ROOT/'workers/chrono/third_party/Chrono-LICENSE.txt',ROOT/'workers/chrono/build-dependencies-osx-arm64.lock']
    files=[{'file':str(file.relative_to(ROOT)),'sha256':sha(file),'bytes':file.stat().st_size} for file in paths]
    compiler=subprocess.check_output(['/usr/bin/clang++','--version'],text=True).strip()
    config_hash=hashlib.sha256(json.dumps(configuration,separators=(',',':')).encode()).hexdigest()
    content={'version':'9.0.1','upstream_commit':COMMIT,'files':files,'compiler':compiler,'configuration_sha256':config_hash}
    identity=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    upstream_files=['src/chrono_vehicle/terrain/SCMTerrain.cpp','src/chrono_vehicle/terrain/SCMTerrain.h','src/demos/vehicle/terrain/demo_VEH_SCMTerrain_RigidTire.cpp','src/demos/robot/demo_ROBOT_Viper_SCM.cpp','src/chrono_models/robot/viper/Viper.cpp','src/chrono_models/robot/viper/Viper.h','LICENSE']
    record={**content,'software':'Project Chrono CPU SCM reference worker','runtime_identity':identity,'executable':str(executable.relative_to(ROOT)),'built_utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'configuration':configuration,'source_repository':'https://github.com/projectchrono/chrono','upstream_files':[{'file':file,'sha256':sha(SOURCE/file),'url':'https://github.com/projectchrono/chrono/blob/'+COMMIT+'/'+file} for file in upstream_files],'scope':'Independent TREC laboratory reference with declared SCM parameters. Not the paper GPU CRM/SPH engine or calibrated lunar soil.','dynamic_libraries':subprocess.check_output(['/usr/bin/otool','-L',str(executable)],text=True)}
    (ROOT/'data/runtime/chrono-runtime.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'runtime_identity':identity,'executable':str(executable),'libraries':len(libraries)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-core-build',action='store_true')
    build(parser.parse_args().skip_core_build)
