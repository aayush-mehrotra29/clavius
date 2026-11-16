export type Vector3 = [number, number, number];

export interface FlightSamples {
  globe_frames: {
    earth_xyzw: [number, number, number, number][];
    moon_xyzw: [number, number, number, number][];
    sun_direction_j2000: Vector3[];
  };
  times_seconds: number[];
  spacecraft_coords_km: Vector3[];
  spacecraft_velocities_kms: Vector3[];
  moon_coords_km: Vector3[];
  moon_velocities_kms: Vector3[];
  approach_index: number;
  patch_index: number;
  lunar_reference_radius_km: number;
  earth_reference_radius_km: number;
  earth_mu_km3_s2: number;
}
