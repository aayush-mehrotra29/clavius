from types import SimpleNamespace

import numpy as np

from clavius.terrain import Site, horizon_distances


def test_narrow_local_ridge_beyond_one_km_can_occlude_the_sun():
    """A 10 m wide ridge at 1,040 m fell between the former 80 m steps."""
    class Probe:
        local = SimpleNamespace(pixel_m=5., width=3200, height=3200)
        regional = SimpleNamespace(pixel_m=80., sample=lambda x, y: np.zeros_like(x))
        horizon_directions = Site.horizon_directions

        def sample(self, east, north):
            return {"covered": True, "lat_deg": -90., "lon_deg": 0., "elevation_m": 0.}

        def local_horizon_sample(self, x, y):
            return np.maximum(0., 40 * (1 - np.abs(np.hypot(x, y) - 1040) / 5))

    h = Probe().horizon_directions(0, 0, [0], observer_height=0)[0]
    assert h > 2  # A solar center at 1 degree is shadowed by this ridge.
    refined = Probe().horizon_directions(0, 0, [0], observer_height=0, refinement=2)[0]
    assert abs(h - refined) < .001


def test_native_sampling_covers_diagonal_of_local_patch_and_retains_far_context():
    local = SimpleNamespace(pixel_m=5., width=3200, height=3200)
    regional = SimpleNamespace(pixel_m=80.)
    distances = horizon_distances(local, regional)
    interior = distances[(distances >= 1000) & (distances <= 22500)]
    assert np.max(np.diff(interior)) <= 5
    assert distances[-1] == 220000
    coarse_regional = horizon_distances(SimpleNamespace(pixel_m=80.), regional)
    assert len(coarse_regional) < len(distances)
