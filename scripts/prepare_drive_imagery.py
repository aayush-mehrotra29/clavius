"""Project an LROC controlled south-pole average mosaic into each drive site's ENU grid."""
from pathlib import Path
import hashlib
import json
import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from rasterio.windows import Window
from backend.clavius.terrain import Site, stereographic

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"public/data/drive"
PRODUCT = "NAC_POLE_SOUTH_CM_AVG_P892S2250"
SOURCE = ROOT/"data/raw/nac-drive"/(PRODUCT+".TIF")
EXPECTED = "c2efa377c1a158ea170242f84f6a88b7c5c2286da2d470150b6b0572459b31b1"
URL = "https://pds.mcp.nasa.gov/data/store/img/lunar_reconnaissance_orbiter/pds4/lroc/lro-l-lroc-5-rdr/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_SOUTH_CM_AVG/"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def project(src,site,level,half,spacing):
    # Pixel centers on the same tangent plane as the terrain. PNG row 0 is north.
    count=2*half//spacing
    axis=-half+(np.arange(count)+.5)*spacing
    rgba=np.zeros((4,count,count),dtype="uint8")
    for j in range(0,count,64):
        e,n=np.meshgrid(axis,-axis[j:j+64])
        x,y=stereographic(*site.location(e,n))
        col=np.floor((x-src.transform.c)/src.transform.a).astype(int)
        row=np.floor((y-src.transform.f)/src.transform.e).astype(int)
        covered=(col>=0)&(row>=0)&(col<src.width)&(row<src.height)
        if not covered.any():
            continue
        i0,i1=col[covered].min(),col[covered].max()
        j0,j1=row[covered].min(),row[covered].max()
        tile=src.read(1,window=Window(i0,j0,i1-i0+1,j1-j0+1))
        v=np.zeros_like(col,dtype="uint8")
        v[covered]=tile[row[covered]-j0,col[covered]-i0]
        rgba[:3,j:j+len(e)]=v
        rgba[3,j:j+len(e)]=np.where(covered&(v>0),255,0)
    path=OUT/f"{site.id}-{level}-nac.png"
    with rasterio.open(path,"w",driver="PNG",width=count,height=count,count=4,dtype="uint8") as dst:
        dst.colorinterp=(ColorInterp.red,ColorInterp.green,ColorInterp.blue,ColorInterp.alpha)
        dst.write(rgba)
    return dict(file=path.name,sha256=sha(path),spacing_m=spacing,half_extent_m=half,
                valid_pixels=int(np.count_nonzero(rgba[3])),total_pixels=count**2)


def main():
    if sha(SOURCE)!=EXPECTED:
        raise ValueError("Unexpected LROC GeoTIFF")
    record=dict(product=PRODUCT,source_url=URL+SOURCE.name,source_sha256=EXPECTED,
                bytes=SOURCE.stat().st_size,
                catalogue="https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG",
                credit="NASA/GSFC/Arizona State University; Archinal et al. (2023)",
                acquisition="Multi-image average composite; no single mission UTC",
                method="Nearest source pixel at ENU display pixel center. Preserve browse intensity. Outside this tile and DN 0 are transparent; the browse TIFF declares no nodata, so zeros are conservatively excluded.",
                role="historical visual texture only", script="scripts/prepare_drive_imagery.py",sites={})
    with rasterio.open(SOURCE) as src:
        assert src.shape==(45488,45488) and src.transform.a==1 and src.transform.e==-1
        record.update(transform=list(src.transform)[:6],native_posting_m=1,crs_wkt=src.crs.to_wkt())
        for name in ("connecting-ridge","shackleton-rim"):
            site=Site(name)
            record["sites"][name]={level:project(src,site,level,half,spacing) for level,half,spacing in
                                  [("drive",1280,1),("horizon",20480,20)]}
    (OUT/"imagery.json").write_text(json.dumps(record,indent=2)+"\n")

if __name__=="__main__":
    main()
