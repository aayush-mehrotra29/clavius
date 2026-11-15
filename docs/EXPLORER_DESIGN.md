# Clavius explorer direction

Brief: a local web workspace for the first lunar simulation foundation. The landing page stays intentionally empty apart from identity and entry. The explorer puts actual lunar imagery and geometry first.

Reference lock: Refero's bundled Typography and Craft Details guides (live Refero is unavailable due to an inactive subscription), the existing NASA-data handoff, and NASA SVS CGI Moon Kit. Work-tool neutrality, compact readable metadata, one system sans family, tabular coordinate values, semantic buttons and a URL that preserves the selected region. Use a near-black canvas to give the Moon room, thin neutral dividers to structure tools, and a pale green accent only for active selections/actions. No marketing sections, ornamental gradients, invented scientific readouts, or generated lunar imagery.

| Decision | Source | Role | Reason |
| --- | --- | --- | --- |
| Empty entry page | User brief | App entry | Placeholder landing requested |
| Persistent region browser and full-height viewport | User brief and Craft Details navigation | Region selection | Keep exploration in view |
| System sans and monospace numerals | Typography guide | Work UI and scientific values | Readability and stable data alignment |
| Black canvas, actual Moon texture | NASA Moon Kit and subject | Scientific media | Surface features remain the focus |
| Selected-site green ring and green primary action | Selection state | Interaction only | Visible target without recoloring the NASA texture |
| Native geometry and disclosed display amplification | NASA Moon Kit | Elevation | Preserve quantitative heights while allowing readable relief |
| Source dialog and resolution disclosure | Repository handoff | Data provenance | Global data does not establish wheel-scale hazards |

QA target: large, detailed globe framed by restrained controls; compact region list; selected-region readout; responsive layout; keyboard and touch navigation; working data loading and error states.

## Verification

- Production Vite build succeeds.
- Six Node tests cover spherical coordinate orientation/round trips, NASA elevation decoding, longitude seam continuity, polar sample clamping, elevation asset hash/physical range and corrupted asset rejection.
- Aside browser QA: landing-to-app navigation; loaded NASA globe; Clavius regional mesh; south-pole filtering and Shackleton mesh; 390 × 844 responsive layout; mobile region drawer, text search and selection; layer switching; vertical exaggeration with unchanged numerical elevation; keyboard terrain movement; click-to-pin coordinates and URL updates.
- QA changes: unwrap regional mesh UVs per triangle at longitude seams; improve control contrast over terrain; honor reduced-motion preferences for globe flights; dispose GPU resources on navigation; remove hidden mobile controls from keyboard interaction.

The lock is preserved: minimal entry, compact tool UI, NASA-derived imagery as the main visual, thin panel boundaries, and accent reserved for active selection and navigation.


## Terrain clarity update — 14 November 2026

The existing rendered terrain and the user's request to define it more clearly are the reference for this focused update. Keep the interface and NASA imagery intact; improve the actual elevation cues rather than inventing surface texture.

- Use native-DEM finite-difference surface normals for per-pixel relief. The same LOLA input remains authoritative; RGB8 normals are a display derivative only.
- Reduce ambient fill, use lower-angle directional lighting and tone mapping, and cast illustrative regional mesh shadows to separate crater walls from floors.
- Increase the globe mesh to 768 × 384 segments and regional mesh to 256 × 256 segments. This changes display sampling, not measured resolution.
- Add a sun-elevation slider alongside the existing display settings; leave true height scale at 1× and keep numerical elevation unchanged.
- Preserve the camera when changing exaggeration.
- Record active sources in `docs/NASA_DATASETS.md`, link derivatives to the DEM hash in `public/data/manifest.json`, and retain a dataset-continuity instruction in `AGENTS.md`.

Validation: seven Node tests (including derivative provenance), four analytical Python normal tests, production build, and browser comparison of the original/updated Clavius regional view. Directional shading is demonstrably stronger at 1×; no NASA elevation samples changed.
