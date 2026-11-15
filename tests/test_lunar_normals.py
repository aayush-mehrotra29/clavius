"""Analytical checks for the DEM-derived shading asset."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from derive_lunar_normals import surface_normals, RADIUS_M


class NormalTests(unittest.TestCase):
    def test_constant_height_sphere_normals_are_radial(self):
        heights = np.full((32, 64), 1000., dtype=np.float32)
        normals = surface_normals(heights)
        lat = np.pi/2 - (np.arange(32)+.5)*np.pi/32
        lon = -np.pi + (np.arange(64)+.5)*2*np.pi/64
        expected = np.stack(np.broadcast_arrays(
            np.cos(lat)[:,None]*np.cos(lon),
            np.sin(lat)[:,None]+np.zeros((32,64)),
            -np.cos(lat)[:,None]*np.sin(lon)), axis=-1)
        np.testing.assert_allclose(normals, expected, atol=1e-6)

    def test_north_rising_surface_tilts_normals_south(self):
        h, w = 128, 256
        lat = np.pi/2 - (np.arange(h)+.5)*np.pi/h
        lon = -np.pi + (np.arange(w)+.5)*2*np.pi/w
        heights = np.broadcast_to(lat[:,None]*RADIUS_M*.04, (h,w))
        normals = surface_normals(heights)
        row, col = h//2, w//2
        north = np.array([-np.sin(lat[row])*np.cos(lon[col]), np.cos(lat[row]), np.sin(lat[row])*np.sin(lon[col])])
        self.assertLess(np.dot(normals[row,col], north), -.035)
        self.assertGreater(np.dot(normals[row,col], north), -.045)

    def test_east_rising_periodic_surface_and_seam(self):
        h, w = 64, 512
        lon = -np.pi + (np.arange(w)+.5)*2*np.pi/w
        heights = np.broadcast_to(5000*np.sin(lon), (h,w))
        normals = surface_normals(heights)
        lat = np.pi/2 - (h//2+.5)*np.pi/h
        col=w//2
        east = np.array([-np.sin(lon[col]),0,-np.cos(lon[col])])
        self.assertLess(np.dot(normals[h//2,col],east), 0)
        # Continuous normals and no one-sided longitude seam spike.
        self.assertLess(np.linalg.norm(normals[h//2,0]-normals[h//2,-1]), .015)
        np.testing.assert_allclose(np.linalg.norm(normals,axis=-1),1,atol=1e-6)

    def test_polar_rows_remain_finite_and_unit_length(self):
        rng=np.random.default_rng(42)
        normals=surface_normals(rng.uniform(-5000,5000,(64,128)))
        self.assertTrue(np.isfinite(normals).all())
        np.testing.assert_allclose(np.linalg.norm(normals,axis=-1),1,atol=1e-6)


if __name__ == '__main__':
    unittest.main()
