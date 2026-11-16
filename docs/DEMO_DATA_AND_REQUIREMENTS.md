# Clavius demo requirements and dataset notes

Checked 15 November 2026 against the current working code, the two dataset manifests, the challenge Details and Resources tabs, and the official submission and judging guides. Companion to the [narrated demo script](DEMO_SCRIPT.md). This is a presentation reference, not a change to the scientific validation records.

## Official requirements and presentation focus

The [Lunar Landing Site Navigator challenge](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/) centers on accessible comparison of lunar locations and dates, with Sun and Earth positions against the horizon informing energy and direct-to-Earth visibility. Its detailed feature ideas and technical considerations are suggestions rather than a mandatory implementation checklist. The script leads with the working site/date comparison.

The challenge's [Resources tab](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/?tab=resources) links Quickmap, Moon Trek, JPL Horizons and CSA Moon Exploration. Clavius performs its own terrain and SPICE calculations; it is not an embedded Quickmap or Moon Trek interface. It uses retained Horizons replies for an external geometry comparison. The CSA portal is a suggested challenge resource, not an ingested Clavius dataset.

The [2026 Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/), dated 13 November 2026, sets the Project Demo limit at 30 seconds for video or seven slides including title and introduction. Materials must be accessible without an account or permission request. English is required, with English subtitles permitted for a demo spoken in another language. Complete the project description, NASA-data account and external-resource credits; identify actual SI/AI tool use and generated media as instructed. Global-award eligibility requires at least one NASA data source or resource. The guide excludes likenesses of people under 18 from project demonstrations and final projects; an application-only recording avoids putting people on screen. Submission closes at 11:59 p.m. on 15 November in the registered Local Event's time zone, or the Team Owner's local time for the Universal Event; local judging can have a different deadline. The full app walkthrough is separate from the limited Project Demo.

The [2026 Judging and Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/) evaluates Impact, Creativity, Validity, Relevance and Presentation on a 1–5 scale. Demonstrate audience value, the linked comparison workflow, concrete data use and honest validation limits. Do not claim measured improvements in planning time or operational adoption without evidence.

## Challenge coverage in the current application

| Challenge topic | What to show | Scope |
| --- | --- | --- |
| Compare locations and dates | `/app` landing search, both sites and three dates | Six nominal site/date options; three transfer durations per option. Arbitrary-coordinate physics is unavailable. |
| Choose mission priorities | Balance, solar energy, Earth contact or Δv; optional limits | Transparent ranking within the evaluated set. No global optimum or safe-landing certification. |
| Sun and Earth relative to the horizon | Local-horizon plot, scrubber and next-event readout | 0.5 m observer; actual-azimuth terrain rays. The 4° skyline is a display sample. |
| Assess solar potential | Elevation, disk fraction, equivalent sunlight, level/tracking incident energy | Wh/m² precedes conversion losses. Rover watts and battery Wh use additional assumptions in their own workflows. |
| Assess communication opportunities | Earth visibility, outage and UTC-window bands | Geometric Earth-center clearance. No RF link, ground-network scheduling or relay analysis. |
| Explore temporal changes | UTC selection and timeline through the surface window | Landing-search samples every 10 minutes through 72 h, then 30 minutes for longer windows up to 720 h. Short events can be missed. |
| Multiple visualizations | Horizon chart, atlas, traverse map, flight path, mission replay and analysis | Distinguish imagery and display shading from physics inputs. |
| Serve multiple skill levels | Main workflow first, detailed evidence and simulation lab second | Intended audiences are planners, educators and the public; usability gains have not been measured in a user study. |
| Respond to schedule changes | New comparison; optional lab bounded-alternative search | Main search compares dates/sites; lab repair preserves tasks but does not search new routes/sites. |

## Active source inventory

The authoritative file identities are [the explorer manifest](../public/data/manifest.json), [the simulation manifest](../public/data/simulation-manifest.json), and [NASA_DATASETS.md](NASA_DATASETS.md). The table identifies each source's actual role. Original URLs, source hashes and derivative hashes remain in those records and their linked catalogues.

| Source and exact products | Where and how Clavius uses them | Resolution or convention and limits |
| --- | --- | --- |
| [2019 NASA SVS CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/): LOLA `ldem_16_uint.tif` | Atlas globe geometry, fallback terrain and derived normals | 5,760 × 2,880; 16 px/degree, about 1.9 km north–south. Decode `sample × 0.5 − 10000` m relative to the 1,737.4 km sphere. |
| Same distribution: LOLA `ldem_64_uint.tif` | Streamed atlas regional terrain tiles | 23,040 × 11,520; 64 px/degree, about 474 m north–south. Global coverage; interpolation adds no observations. |
| Same distribution: `lroc_color_poles_8k.tif` and `lroc_color_poles_4k.tif` | 8,192 × 4,096 atlas imagery; 4,096 × 2,048 thumbnail/fallback and flight Moon texture | Visualization mosaic with polar LOLA albedo fill, inpainting and color adjustment. Neither current imagery nor a wheel-scale polar hazard map. |
| [NASA Earth Observatory Blue Marble Next Generation](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/): July 2004 `world.200407.3x5400x2700.jpg` | Earth in flight playback | Static 5,400 × 2,700 monthly composite. SPICE supplies orientation; this texture does not depict mission-date weather. |
| [PGDA78](https://pgda.gsfc.nasa.gov/products/78): `Site01_final_adj_5mpp_surf.tif` and `Site04_final_adj_5mpp_surf.tif` | Connecting Ridge and Shackleton rim nominal terrain, local horizons, picking and native contact geometry | Each 3,200 × 3,200 at 5 m posting. Approximate curated analysis origins, not certified safe landing coordinates. |
| PGDA78: `Site01_final_adj_5mpp_toterr.tif` and `Site04_final_adj_5mpp_toterr.tif` | Height-RMS inspection and evidence | Height uncertainty, not traction or rock labels. |
| PGDA78: `Site04_ROIs.tgz`, record 4 | Shackleton rim analysis origin | Source polar X = −2,657.5 m, Y = −5,957.5 m; about 89.784873915° S, 204.040521234° E. Connecting Ridge uses 89.44° S, 222.8° E. |
| PGDA78: `Site01_final_adj_5mpp_ldec.tif` and `Site04_final_adj_5mpp_ldec.tif` | Native-cell nominal LOLA-return counts and support display | No bilinear averaging of counts. Zero means interpolated nominal terrain; missing support remains unknown. Positive counts do not prove all points in a cell are exact. |
| PGDA78: `Site01_final_adj_5mpp_0001_err.tif` through `0003`, and the matching Site04 files | Lab alternative surfaces; clone 001 also has packaged VIPER terrain, replays, lighting and parked-power scenarios | Six complete 5 m statistical elevation realizations. These are not additive error rasters or new observations. Only three of 100 per site are loaded. Default nominal/001 testing is distinct from 002/003 repair-audit surfaces. |
| [PGDA90](https://pgda.gsfc.nasa.gov/products/90): `LDEM_80S_80MPP_ADJ.TIF` | Regional horizons to 220 km and regional display context | 7,600 × 7,600 at 80 m posting. Regional surface stays nominal when a local clone changes. |
| [JPL NAIF SPICE kernels](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/): `de421.bsp`, `moon_pa_de421_1900-2050.bpc`, `moon_080317.tf`, `naif0012.tls`, `pck00011.tpc` | Local Sun/Earth geometry, lunar orientation, distances, UTC/ET conversion and flight body frames | Pinned DE421 bundle; surface frame `MOON_ME_DE421`, geometric `NONE` aberration convention. Current API epochs span 2000–2049. No atmospheric-refraction model is required for the lunar surface. |
| [LROC controlled south-pole average NAC mosaic](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG): `NAC_POLE_SOUTH_CM_AVG_P892S2250.TIF` | Separate VIPER-drive historical imagery, clipped and reprojected per site | 1 m/pixel source browse tile. Multi-exposure historical shadows and incomplete tile coverage; no added contact geometry. Hidden in mission-sunlight mode. |
| [LROC/DLR ESALL_CR1](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_ESALL_CR1) and [ESALL_SR12](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_ESALL_SR12): `NAC_DTM_<product>.TIF`, `_CONF.IMG`, `_NACMOS_1M.TIF` | Expedition map relief and slope inspection at the two sites | 1 m orthoimagery, 2 m stereo elevations, correlation confidence code 14. Slope uses a 4 m central-difference baseline and confidence-masked interpolation. Display is sampled at 0.5 m; physical contact remains nominal 5 m PGDA78. |
| [LRO Diviner PCP diurnal products](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_pcp/diurnal/ltim/pols/): `pcp_avg_tbol_pols_sum_ltim01_240.tab` and `pcp_avg_tbol_pols_sum_ltim49_240.tab` | Lab historical surface context; optional explicitly selected constant ground boundary | 240 m southern-summer average bolometric brightness temperatures, 00:00–00:15 and 12:00–12:15 lunar local time, using 2009–2019 observations. Separate site clips retain rows and gaps. Not future-epoch forecasts, battery temperatures or ordered daily extremes. |

## Validation inputs and model references

These references support bounded checks or declared model properties. They should not be narrated as additional active lunar measurements.

| Reference | Actual use | Result or remaining limitation |
| --- | --- | --- |
| PGDA90 NAC observations/renderings `M1188426614`, `M1311409938`, `M139729686` and original PDS4 acquisition labels | Dated illumination validation on a 200 m lattice, with local-site checks where supported | Observed I/F and rendered W/m² are different quantities. Two regional dates and one local-site epoch assessed; M1311409938 remains unsupported. Numerical gates are not all met. [Illumination record](ILLUMINATION_VALIDATION.md). |
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/), seven retained replies using DE441 | Independent geometric Sun/Earth direction and range checks at two nominal origins, eight epochs, 32 target comparisons | Maximum angular separation below 0.038 arcsec, Sun range difference below 9.1 m and Earth range difference below 0.28 m. These are pre-occlusion comparisons, not terrain-horizon or shadow accuracy. [Geometry report](../public/data/horizons-geometry.json). |
| [NASA Glenn TREC/MGRU3 publication](https://ntrs.nasa.gov/citations/20250001809) and pinned author plot arrays | Validation-only observations: 18 TREC points, 6 MGRU3 2021 points and 7 MGRU3 2022 points | Published plotting coordinates, not raw telemetry. Independent rigid TREC fixture has 12.83° RMS discrepancy across its 18-point test and fails traction targets. [Source manifest](../public/data/mobility-reference-manifest.json), [record](MOBILITY_VALIDATION.md). |
| Same TREC observations; Project Chrono 9.0.1 CPU SCM | Separate offline 54-case development campaign with frozen ten-point training/eight-point holdout split | Holdout RMS 9.6846° versus rigid 15.6027° on those same eight points. Physical targets and two 40%-slip refinement targets fail. Selected 30°/0.015 m are effective parameters, not measured GRC-3 properties. Neither active soil physics nor the paper's GPU SPH model. [SCM record](SCM_VALIDATION.md). |
| [NASA VIPER hardware briefing](https://ntrs.nasa.gov/citations/20240013903), [2021 project information package](https://science.nasa.gov/wp-content/uploads/2024/08/viper-pip-final.pdf), and [2025 technical briefing](https://assets.science.nasa.gov/content/dam/science/psd/lunar-science/documents/2025-02-13_VIPER_Updated_Technical_Briefing_Presentation-Shared.pdf) | Hardware references for the visual model, steering bounds, three array faces and battery scenario | Dated hardware reference: 447 kg, ±50° steering; recorded mechanical model: 434.9211 kg, 30° bound. Array rating 320 W per face; battery 5,420 Wh at beginning of life and 0 °C. Missing hardware calibration stays explicit. [Audit](NASA_ROBOT_MODELS.md), [visual record](../public/robots/viper/source.json), [battery record](../public/robots/viper/battery.json). |
| Project Chrono upstream VIPER assembly and separate Clavius frame repair | Native rigid-floor probes and packaged straight/crab rigid-contact experiments | Fourteen correction cases pass a bounded frame/torque/control protocol. Frame repair retains mass/steering assumptions; it does not activate a flight-calibrated robot. Manual view, recorded traces and R1 mission solver remain distinct. |
| [NASA GMAT R2026a original sample cases](https://github.com/nasa/GMAT/tree/R2026a/application/samples): `Ex_GivenEpochGoToTheMoon.script`, `Ex_LunarTransfer.script` | Separate executed orbital-reference campaign, using native DE405 support | Reference execution is complete; accepted search, continuous-clearance and descent gates remain incomplete. GMAT uses a 1,738.2 km radius; surface terrain uses 1,737.4 km. The app flight rehearsal is a separate implementation. [GMAT record](GMAT_REFERENCES.md). |
| [NASA thermal-control guide](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/) | Conceptual reference for optional single-node vacuum heat balance | Supplies no Clavius hardware properties or instantaneous lunar temperature raster. [Thermal model](THERMAL_MODEL.md). |
| Official JPL Perseverance visualization URDF | Source audit only | Zero mass/tensors and missing colliders prevent physical support. No substitution of R1 properties and no active Perseverance mission model. [Robot source audit](validation/nasa-robot-source-audit.json). |

## Derived assets and implementation credits

- `lola-normals.png`, terrain tiles, site meshes, categorical support PNGs, map rasters and landing previews are Clavius display/processing derivatives. Their source and output identities are recorded. Normals, procedural material grain, extra vertices, texture resampling, lighting and vertical exaggeration add no measured terrain detail.
- The drive [terrain](../public/data/drive/index.json), [imagery](../public/data/drive/imagery.json), [replay](../public/data/drive/replays.json), [sunlight](../public/data/drive/sunlight.json), [terrain-comparison](../public/data/drive/viper-terrain-comparison.json) and [traverse-relief](../public/data/drive/traverse-relief.json) catalogues connect packaged outputs to their inputs. Parked series and clone parking cases are linked through both top-level manifests.
- Four nominal plus four clone-001 native drives each last 20 s. Their 17 body transforms, wheel reductions and sunlight series are simulation outputs. Packaged starts are noon UTC on 1, 21 and 27 January 2028; changing the lighting date does not rerun the trajectory. Custom/live lighting needs the service.
- The frontend uses JavaScript/TypeScript, React, Three.js and Recharts; the service uses Python/FastAPI, NumPy/SciPy and SPICE. MuJoCo, Gazebo Harmonic/DART/ROS 2, and Chrono serve distinct dynamics or experimental roles. Cite actual dependency versions through the lockfiles and evidence records.
- The flight canvas and trajectory charts adapt [Aditya's flight simulator and trajectory analysis](https://github.com/prollyAditya/Clavius/tree/3f26903fad64ae961b1464597d83d3a86ef02663/frontend/src/components/views). Retain that attribution in the submission alongside third-party code and data references.
- Credit NASA SVS, Ernie Wright, LRO/LOLA/LROC teams, the PGDA authors, LROC/DLR stereo producers, the Diviner team and PDS archive, JPL NAIF/Horizons, NASA Earth Observatory/MODIS, and the cited robot, software and experimental-source authors. The exact citations in the source records take precedence over abbreviated spoken credits.

## Judge answers

**What is the main contribution?** Accessible comparison of six curated site/date options, with a terrain horizon, solar potential, Earth visibility and a linked flight/surface rehearsal. NASA elevations and ephemerides participate in the calculation.

**Does it find a safe landing site anywhere on the Moon?** The atlas supports global browsing and pins. The physics workflows use two curated origins, and no landing-footprint safety or sub-grid hazard qualification is established.

**Is the flight dynamically validated through touchdown?** The application checks targeted point-mass coast endpoints and central reference-sphere clearance, then prescribes descent. This does not establish thrust/fuel feasibility, full terrain clearance or dispersions. GMAT reference results are separate.

**Is the rover NASA VIPER?** The mission built-in is hypothetical R1. The separate drive contains a VIPER visual reference and native component replays with documented assumptions. Corrected mechanical frames do not resolve all hardware, control, soil, power and thermal discrepancies.

**Does Earth in view mean a working radio?** It means the Earth's geometric center clears the modeled terrain. Antenna pointing, RF margin, stations and relays require further modeling.

**Is a thermal value a forecast?** Diviner supplies two historical surface composites. The optional thermal node uses declared hardware and a constant boundary. Neither establishes future battery temperature.

**What does the uncertainty demonstration prove?** It measures changes under selected statistical terrain reconstructions and declared parameter scenarios. The limited set does not establish failure probabilities or complete distribution tails.

**Can judges run everything on the public frontend?** Atlas, packaged drive/replay assets and their precomputed context can run statically. The current deployment configuration explicitly returns unavailable responses for backend computation. Landing searches, new flights/traverses, lab runs, imports and custom lighting require the Python service. Provide an actual recording and the source/setup instructions; do not imply a live hosted backend. See [deployment notes](DEPLOYMENT.md).

## Claim review and recording checks

| Avoid | Use |
| --- | --- |
| “The safest or optimal lunar landing site” | “The best evaluated option under these inputs and limits” |
| “NASA-calibrated rover simulation” | “Rigid-contact simulation with documented assumptions” |
| “VIPER completed our planned mission” | “The hypothetical R1 completed this simulated traverse” |
| “A guaranteed communications window” | “A sampled Earth-center visibility window” |
| “A live NASA Moon feed” | “Historical imagery and locally calculated geometry” |
| “Half-meter physical terrain” | “A display/interpolation grid derived from five-meter measured posting” |
| “Future battery temperature from Diviner” | “Historical Diviner context and an optional declared thermal scenario” |
| “Validated landing/descent” | “Targeted transfer rehearsal with prescribed descent” |
| “Calibrated lunar regolith” | “Rigid contact; separate soil-model development still misses acceptance targets” |
| “All features are available on the hosted site” | “Static features ship; calculations need the separate service” |

The documentation review checked the current entry-point routes, landing ranking and sampling code, flight implementation, waypoint/dwell controller, Mission analysis, lab controls, drive models, source catalogues and validation records. An integrity check verified 27 unique public file references carrying URL/SHA-256 pairs in the two top-level manifests; all matched. The shared `rover_drive`, `traverse_relief` and `horizons_geometry` records agreed between manifests. This check covered those packaged references, not a fresh download or independent verification of every original NASA source.

The reviewed application baseline includes commit `c034343`, which adds the unified Mission analysis report. Record from the tested working application and recheck the deployed version before publishing its capabilities. This writing task did not rerun the full native campaign or create a new browser acceptance record. Existing scientific failures remain as documented in their source reports.
