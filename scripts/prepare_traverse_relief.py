"""Bake the two traverse display layers onto the nominal rover surface."""
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from scipy.ndimage import map_coordinates, minimum_filter, spline_filter
from backend.clavius.terrain import Site, stereographic

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data/drive"
RAW = ROOT / "data/raw/traverse-stereo"
ARCHIVE = "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001"
SITES = {
    "connecting-ridge": ("ESALL_CR1",
        "fc57e2d4452bf2522ae7ed3a091e4f6dfc4eea6a989324edb06344689712a453",
        "c1847418d7756b47d0abaeaea95e6f8c8af233924494c12f6b9fc33528b25410",
        "2b399a480f648170db35b51934710068c234125cabcd5f1fa4694e43c0a9ff44"),
    "shackleton-rim": ("ESALL_SR12",
        "52d35898a61991bb13bd463156bd95a8c01be6806247247e891752f56fbb425c",
        "fa312cd5ddc2c8322d5ac7e73968a84f89d3aa72da17358fe47f513efe15e8f0",
        "12f5517bcb55ede2090ac20f844624bece8934aec5467a15cf07df8cfb74815f"),
}
TILT = 34
HALF = 512
PITCH = 0.5


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(product, suffix, published, directory, expected):
    path = RAW / (product + suffix)
    if digest(path) != expected:
        raise ValueError(f"Source hash mismatch: {path}")
    with rasterio.open(path) as src:
        data = src.read(1)
        transform = src.transform
        crs = src.crs.to_dict()
        assert crs["proj"] == "stere" and crs["lat_0"] == -90 and crs["lon_0"] == 0
        record = dict(url=f"{ARCHIVE}/{directory}/NAC_DTM/{product}/NAC_DTM_{product}{published}",
                      sha256=expected, bytes=path.stat().st_size, spacing_m=transform.a,
                      transform=list(transform)[:6], nodata=src.nodata, local_file=path.name)
    return data, transform, record


def coordinates(transform, x, y):
    return np.stack([(y-transform.f)/transform.e-.5, (x-transform.c)/transform.a-.5])


def sample(values, coords, order=1):
    return map_coordinates(values, coords, order=order, mode="constant", cval=0, prefilter=False)


def write_layer(site, name, array):
    path = OUT / f"{site}-traverse-{name}.png"
    bands = array[None,:,:] if array.ndim == 2 else array.transpose(2,0,1)
    with rasterio.open(path, "w", driver="PNG", width=array.shape[1], height=array.shape[0],
                       count=len(bands), dtype="uint8") as dst:
        dst.colorinterp = (ColorInterp.gray,) if len(bands) == 1 else (ColorInterp.gray, ColorInterp.alpha)
        dst.write(bands)
    return dict(file=path.name, sha256=digest(path), bytes=path.stat().st_size)


def prepare(site_id, drive):
    prod, zhash, chash, ihash = SITES[site_id]
    z, zt, zr = source(prod, ".TIF", ".TIF", "DATA/SDP", zhash)
    conf, ct, cr = source(prod, "_CONF.IMG", "_CONF.IMG", "DATA/SDP", chash)
    photo, pt, pr = source(prod, "_ORTHO.TIF", "_NACMOS_1M.TIF", "EXTRAS/BROWSE", ihash)
    assert ct == zt and zt.a == 2 and pt.a == 1 and z.shape == conf.shape
    # Only use gradients whose full central-difference stencil has stereo support.
    good = (conf == 14) & (z != zr["nodata"])
    z[~good] = 0
    gn, ge = np.gradient(z, zt.e, zt.a)
    supported = minimum_filter(good.astype(np.uint8), size=3).astype(np.float32)
    grade = np.degrees(np.arctan(np.hypot(ge, gn)))
    # Unit normal dotted with an illustrative light in the source map's NW quadrant.
    lighting = (.5*ge - .5*gn + np.sqrt(.5)) / np.sqrt(1 + ge**2 + gn**2)
    # Cubic interpolation of the orthoimage; check the full interpolation neighborhood.
    photo_support = minimum_filter((photo != 0).astype(np.uint8), size=5)
    intensity = spline_filter(photo, output=np.float32)
    site = Site(site_id)
    terrain = next(level for level in drive["levels"] if level["level"] == "drive")
    path = OUT / terrain["file"]
    assert digest(path) == terrain["sha256"]
    count, step, half = terrain["count"], terrain["spacing_m"], terrain["half_extent_m"]
    ground = np.fromfile(path, "<f4").reshape(count, count)
    angle = np.radians(TILT)
    c, s = np.cos(angle), np.sin(angle)
    assert np.min(np.diff(ground, axis=0)/step)*s + c > 0
    axis = np.arange(-HALF + PITCH/2, HALF, PITCH)
    # Intersect each image column with the same triangular facets as groundHeight().
    # At a fixed easting the facet edges fall on grid rows and cell diagonals.
    inv_n = np.empty((len(axis), len(axis)), dtype=np.float32)
    rows = np.arange(count)*step - half
    for k, east in enumerate(axis):
        gx = (east+half)/step
        i = int(gx)
        f = gx-i
        ends = ground[:,i]*(1-f) + ground[:,i+1]*f
        diagonal = ground[:-1,i+1]*f + ground[1:,i]*(1-f)
        north = np.empty(2*count-1)
        height = np.empty_like(north)
        north[::2], north[1::2] = rows, rows[:-1]+(1-f)*step
        height[::2], height[1::2] = ends, diagonal
        projected = north*c + height*s
        assert projected[0] < -HALF and projected[-1] > HALF
        inv_n[:,k] = np.interp(-axis, projected, north)
    relief = np.zeros((len(axis),len(axis),2), dtype=np.uint8)
    slope = np.zeros(inv_n.shape, dtype=np.uint8)
    for start in range(0,len(axis),64):
        sl = slice(start,start+64)
        x,y = stereographic(*site.location(axis[None,:],inv_n[sl]))
        p, d = coordinates(pt,x,y), coordinates(zt,x,y)
        # Require every sample that contributes to the interpolated slope to be supported.
        valid = sample(supported,d) >= .999999
        shade = np.where(valid, sample(lighting,d), np.sqrt(.5))
        brightness = np.clip(sample(intensity,p,3),0,255)
        tone = 255 * np.arcsinh(brightness/38) / np.arcsinh(215/38)
        relief[sl,:,0] = np.clip(tone*(1 + .95*(shade-np.sqrt(.5))),0,255).round()
        relief[sl,:,1] = 255*(sample(photo_support,p,0) == 1)
        slope[sl] = np.where(valid,1+np.minimum(254,np.rint(4*sample(grade,d))),0)
    assert slope[len(axis)//2,len(axis)//2] and relief[len(axis)//2,len(axis)//2,1]
    return dict(product=prod, latitude_deg=site.lat, longitude_deg=site.lon, catalogue=f"https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_{prod}",
                sources=dict(stereo=zr,confidence=cr,ortho=pr), terrain_sha256=terrain["sha256"],
                relief=write_layer(site_id,"relief",relief), slope=write_layer(site_id,"slope",slope))


if __name__ == "__main__":
    drive = json.loads((OUT/"index.json").read_text())["sites"]
    catalog = dict(credit="NASA/GSFC/Arizona State University; ESA Lunar Lander stereo products by DLR.",
                   script="scripts/prepare_traverse_relief.py",
                   tilt_deg=TILT, half_extent_m=HALF, display_pitch_m=PITCH,
                   projection="Orthographic (east, north*cos(tilt) + nominal ENU up*sin(tilt)).",
                   slope_encoding="0 unavailable; (DN-1)/4 degrees, saturated at 63.5 degrees.",
                   sites={key:prepare(key,drive[key]) for key in SITES})
    (OUT/"traverse-relief.json").write_text(json.dumps(catalog,indent=2)+"\n")
