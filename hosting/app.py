"""Vercel ASGI entrypoint; local launchers keep their existing behavior."""
import os,sys
from pathlib import Path

os.environ['CLAVIUS_HOSTED']='1'
os.environ['CLAVIUS_STORAGE']='vercel-blob'
os.environ['CLAVIUS_RUNTIME']='/tmp/clavius'
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('MUJOCO_GL','disable')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from clavius.api import app
