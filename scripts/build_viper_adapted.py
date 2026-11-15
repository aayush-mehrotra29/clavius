"""Build a separately named VIPER mechanical correction from pinned source.

Only two source files are copied and patched in private runtime storage. The
original Chrono checkout, libraries and completed reference runtime stay intact.
"""
from __future__ import annotations

from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

from planner.validation.scm import ROOT,digest,verified_runtime

SPEC=ROOT/'workers/chrono/viper-adapted/model.json'
GENERATED=ROOT/'data/runtime/viper-adapted-source'
BUILD=ROOT/'data/runtime/viper-adapted-build'
INVENTORY=ROOT/'data/runtime/viper-adapted-runtime.json'


def build():
    _,original=verified_runtime()
    spec=json.loads(SPEC.read_text());source=ROOT/'data/raw/robots/chrono'
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
    if head!=spec['upstream_commit'] or dirty:raise ValueError('Pinned original Chrono source differs')
    patch=ROOT/spec['patch']['file']
    if digest(patch)!=spec['patch']['sha256']:raise ValueError('Adaptation patch differs from its specification')
    for item in spec['source_files']:
        file=source/item['file']
        if digest(file)!=item['sha256']:raise ValueError('Pinned model source changed')
        target=GENERATED/item['file'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(file,target)
    subprocess.run(['/usr/bin/patch','--batch','--fuzz=0','-p1','-d',str(GENERATED),'-i',str(patch)],check=True)
    fixture=ROOT/spec['baseline_fixture']['file']
    if digest(fixture)!=spec['baseline_fixture']['sha256']:raise ValueError('Original component fixture changed')
    text=fixture.read_text()
    for old,new in [('#include "chrono_models/robot/viper/Viper.h"','#include "Viper.h"'),('using namespace chrono::viper;','using namespace chrono::clavius_viper;'),('Original upstream VIPER rigid probe completed','Clavius repaired VIPER rigid probe completed'),('Bounded component probe of the original upstream VIPER model.','Bounded component probe of the separately repaired VIPER model.')]:
        if text.count(old)!=1:raise ValueError('Fixture adaptation context changed')
        text=text.replace(old,new)
    (GENERATED/'viper-rigid.cpp').write_text(text)
    cmake=str(ROOT/'data/runtime/chrono-deps/bin/cmake')
    configuration=[cmake,'-S',str(ROOT/'workers/chrono/viper-adapted'),'-B',str(BUILD),'-DChrono_DIR='+str(ROOT/'data/runtime/chrono-build/cmake'),'-DCLAVIUS_VIPER_SOURCE_DIR='+str(GENERATED),'-DCMAKE_BUILD_TYPE=Release']
    subprocess.run(configuration,check=True)
    subprocess.run([cmake,'--build',str(BUILD),'--parallel','1'],check=True)
    executables={name:str((BUILD/filename).relative_to(ROOT)) for name,filename in [('frames_original','clavius_viper_frames_original'),('frames_repaired','clavius_viper_frames_repaired'),('rigid_repaired','clavius_viper_rigid_repaired')]}
    paths=[ROOT/path for path in executables.values()]
    paths+=[BUILD/'libclavius_viper_repaired.a',SPEC,patch,ROOT/'workers/chrono/viper-adapted/CMakeLists.txt',ROOT/'workers/chrono/viper-adapted/frames.cpp',Path(__file__).resolve(),ROOT/'workers/chrono/third_party/Chrono-LICENSE.txt',*sorted(GENERATED.rglob('*.cpp')),*sorted(GENERATED.rglob('*.h')),*sorted((source/'data/robot/viper/col').glob('*.obj'))]
    paths += [ROOT/item['file'] for item in original['files'] if item['file'].endswith('.dylib')]
    files=[{'file':str(file.relative_to(ROOT)),'sha256':digest(file),'bytes':file.stat().st_size} for file in paths]
    compiler=subprocess.check_output(['/usr/bin/clang++','--version'],text=True).strip()
    content={'id':spec['id'],'upstream_commit':head,'reference_runtime_identity':original['runtime_identity'],'files':files,'compiler':compiler,'configuration':configuration}
    identity=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    record={**content,'runtime_identity':identity,'built_utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'executables':executables,'model':spec,'dynamic_libraries':{name:subprocess.check_output(['/usr/bin/otool','-L',str(ROOT/path)],text=True) for name,path in executables.items()},'scope':'Isolated mass/shaft-frame correction; no active app or flight/soil calibration.'}
    INVENTORY.write_text(json.dumps(record,indent=2)+'\n')
    verified_runtime()
    print(json.dumps({'runtime_identity':identity,'model_id':spec['id'],'reference_runtime_unchanged':True}),flush=True)
    return record


if __name__=='__main__':build()
