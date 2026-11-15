# Terrain surface and source support controls

Extend Clavius's existing simulation workspace for rover engineers comparing uncertainty cases. Direct build is locked to the existing site selector, native terrain-layer select, Inter/monospace numerical text, compact source dialogs, green primary actions, blue plots and amber missing-evidence states. Earlier Refero research returned `NO_SUBSCRIPTION`; the same product reference and bundled form/focus craft guidance remain the reference for this small extension.

| Decision | Reference and purpose |
| --- | --- |
| Terrain surface select beside site/time | Existing site control; make nominal versus statistical clone explicit before running |
| Selected clone label on the map | Existing PGDA site label; identify the displayed surface without opening a dialog |
| Nominal LOLA support layer and native-count point inspector | Existing slope/RMS layers and unit-labelled inspector; distinguish returns from interpolation, not safety |
| Missing support uses amber and fails required calculations | Existing unknown-data state; no zero filling or nominal substitution for missing local clone cells |
| Saved replay restores site and selected surface | Existing multi-site replay contract; geometry must match the numerical trajectory |
| Site and surface rows in comparisons | Existing comparison table; reveal the inputs behind numerical differences |
| Default sweeps use nominal/001, repair audits reserve 002/003 | Frozen audit workflow; keep audit surfaces outside nominal candidate selection |

These are published modeled surfaces, not three extra measured maps. Keep that distinction visible beside the control and in source/export records. Counts describe nominal native cells; a positive count does not imply rover-scale hazard coverage. Verify desktop and narrow-screen controls, clone replay, source labels, support layers, export reproduction and the physics engine dialog.

The support layer maps a full native-cell image through source polar coordinates, with nearest filtering and no mipmaps. Vertex color blending is unsuitable for this categorical evidence because it spreads the apparent return support beyond a native cell. Numeric count lookup remains the authority. Texture bytes are hash-checked before use; an unavailable image/GPU disables that visual layer while numerical counts remain available.
