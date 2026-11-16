import numpy as np
from scripts.viper_wheels import reduce_wheel, terrain_normals


def test_wheel_window_uses_only_supported_steps_for_speeds():
    grid = np.zeros((513,513))
    state = np.zeros((100,5,3))
    state[:,3,1] = 1                   # CAD axle in world frame
    state[:25,4,2] = 200
    state[:25,2,1] = .4                # 0.1 m/s rim speed
    state[:25,1] = [.08,-.02,0]
    state[25:,1,0] = 4                 # airborne motion
    result = reduce_wheel(state,grid)
    np.testing.assert_allclose(result[0],[100,.5,.1,.08,-.02])
    np.testing.assert_equal(result[1],[0,0,np.nan,np.nan,np.nan])


def test_facet_gradient_uses_collision_triangle_diagonal():
    grid = np.zeros((513,513))
    grid[257,257] = 5
    normals = terrain_normals(grid,np.array([[1,1,0],[4,4,0]]))
    np.testing.assert_allclose(normals,[[0,0,1],np.array([-1,-1,1])/np.sqrt(3)])
