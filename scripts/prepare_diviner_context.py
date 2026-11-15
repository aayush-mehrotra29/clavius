"""Derive the content-pinned native-record Diviner context clip (no interpolation).

Run scripts/setup_simulation.py --diviner first to obtain the original tables.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from clavius.integrity import verify_sources
from clavius.diviner import derive,selected_specification
spec=verify_sources('diviner')
for key in ['connecting-ridge',*spec.get('additional_derivatives',{})]:
 selected=selected_specification(spec,key);print(derive(selected,ROOT/'data/raw/diviner',ROOT/'public'/selected['derivative']['file']))
