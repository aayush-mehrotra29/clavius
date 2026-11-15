from pathlib import Path
import os
ROOT=Path(os.environ.get('CLAVIUS_ROOT',str(Path(__file__).resolve().parents[2])))
DATA=ROOT/'data'
RUNTIME=Path(os.environ.get('CLAVIUS_RUNTIME',str(DATA/'runtime')))
for p in [RUNTIME,RUNTIME/'artifacts',RUNTIME/'robots']:
 p.mkdir(parents=True,exist_ok=True)
