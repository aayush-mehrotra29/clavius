"""Immutable NASA GMAT reference cases; uploaded scripts never execute."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCES = ROOT / 'planner/orbital/references'
CASES = {
    'fixed-epoch': {
        'file': 'Ex_GivenEpochGoToTheMoon.script',
        'spacecraft': 'MoonSat',
        'moon_frame': 'MoonInertial',
        'targets': [
            [('MoonSat.EarthMoonRot.RA', 0., 1., 'deg'), ('MoonSat.EarthMoonRot.DEC', 0., 1., 'deg')],
            [('MoonSat.Luna.RMAG', 15000., .1, 'km'), ('MoonSat.MoonInertial.BVectorAngle', 75., .1, 'deg'), ('MoonSat.Luna.ECC', .01, .1, 'dimensionless')],
        ],
        'physical_commands': {'departure': 20, 'encounter': 21, 'capture': 25, 'post_capture': 28},
        'physical_command_names': {'departure': ('Maneuver', 'Apply TOI'), 'encounter': ('Propagate', 'Prop To Moon'), 'capture': ('Maneuver', 'Apply LOI'), 'post_capture': ('Propagate', 'Prop .5 days')},
        'post_capture_days': 4.,
        'coarse_initialization_commands': [7, 10],
        'encounter_guards': {'maximum_elapsed_days': 6., 'minimum_radius_km': 1000.},
    },
    'lunar-transfer': {
        'file': 'Ex_LunarTransfer.script',
        'spacecraft': 'Sat',
        'moon_frame': 'MoonMJ2000Eq',
        'targets': [
            [('Sat.MoonMJ2000Eq.BdotT', 15000.4401777, 3., 'km'), ('Sat.MoonMJ2000Eq.BdotR', 4000.59308992, 3., 'km')],
            [('Sat.Luna.ECC', 0., .0001, 'dimensionless')],
        ],
        'physical_command_names': {'departure': ('Maneuver', 'Apply TOI'), 'encounter': ('Propagate', 'Prop to Periselene'), 'capture': ('Maneuver', 'Apply LOI'), 'post_capture': ('Propagate', 'Prop 15 days')},
        'encounter_guards': {},
        'post_capture_days': 15.,
    },
}
