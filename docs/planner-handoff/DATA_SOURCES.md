**Planning datasets and APIs**

Use the IDs below in manifests and run records. Public access is distinct from a promise of service uptime or a blanket reuse license. Preserve product citations, labels, and source-specific terms. NASA archives and the tested Horizons/ODE requests are publicly accessible without a NASA API key.

**1. Required surface datasets**

| ID | Source and exact entry point | Obtain | Purpose and limits |
| --- | --- | --- | --- |
| D01 | [LOLA local terrain and uncertainty, PGDA 78](https://pgda.gsfc.nasa.gov/products/78) | Nominal 5 m grids, counts, slope/height errors, ROI polygons, supplied terrain-error realizations | Local geometry and uncertainty. Statistical terrain realizations are not independent measured surfaces. Grid spacing is not wheel-scale hazard accuracy. |
| D02 | [LOLA regional terrain, PGDA 90](https://pgda.gsfc.nasa.gov/products/90) | Regional elevation COGs plus error/effective-resolution layers; optional roughness and permanently shadowed regions | Distant horizons and regional context. A cropped local patch cannot represent all horizon blockers. |
| D03 | [LROC Connecting Ridge SHACKRDGE02](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_SHACKRDGE02) | DTM, orthophoto, confidence map, labels, README | Local detail/visualization and sensitivity comparisons. DTM posting is 3.5 m; an orthophoto is available at 1.2 m/pixel. Stereo shadows and weak correlations can produce gaps/artifacts. This terrain is tied to LOLA. |
| D04 | [Lunar Polar Illumination, PGDA 69](https://pgda.gsfc.nasa.gov/products/69) | Average sunlight, average Earth visibility and permanent-shadow maps | Site shortlisting and reference comparison. These are modeled long-period statistics, not the requested date's sunlight timeline. Earth visibility can mean any part of Earth's disk is visible. |
| D05 | [NAC observations and simulated images, PGDA 90](https://pgda.gsfc.nasa.gov/products/90) | Published map-projected observed/model scene pairs and acquisition metadata | Observed-shadow validation. Compare boundaries/masks; observed I/F and modeled W/m² should not be compared as identical brightness quantities. |

Start with Site01 Connecting Ridge and a second region from D01. Specific first assets:

- [Site01 nominal terrain](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif)
- [Site01 height RMS error](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_toterr.tif)
- [Site01 ROI polygons](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_ROIs.tgz)
- [Site01 first error realization](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Clones/Site01_final_adj_5mpp_0001_err.tif); obtain the rest from D01 and apply them according to their documented error-field convention.
- [Regional 80 m terrain](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF), with finer/coarser context as needed.
- [SHACKRDGE02 DTM GeoTIFF](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/SHACKRDGE02/NAC_DTM_SHACKRDGE02.TIF)
- [SHACKRDGE02 documentation](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/SHACKRDGE02/NAC_DTM_SHACKRDGE02_README.TXT)
- [M1188426614LE observed scene](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/M1188426614LE_20MPP.TIF) and [published rendering](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/M1188426614_20MPP_MODEL.TIF).

Both PGDA collections use south-polar stereographic horizontal coordinates in metres and MOON_ME/DE421. Product 78's [README](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README) separately documents point-cloud XYZI coordinates in kilometres. Its Z wording needs an explicit importer check before radial conversion. Product 90's associated paper defines heights against a reference sphere; its projection radius is 1737.4 km. Record native and normalized vertical definitions separately. Never apply an Earth EPSG code to lunar data by convenience.

**2. Geometry data and calculation services**

| ID | Resource | Files or endpoint | Use |
| --- | --- | --- | --- |
| G01 | [NAIF SPICE toolkit](https://naif.jpl.nasa.gov/naif/toolkit.html) | Local library plus kernel files below | Reproducible Sun/Earth geometry; this is local computation, not an HTTP visibility API. |
| G02 | [JPL Horizons API docs](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | `https://ssd.jpl.nasa.gov/api/horizons.api` | Prototype geometry and cross-checks. Local terrain occlusion must be computed separately. |
| G03 | [PDS ODE REST](https://oderest.rsl.wustl.edu/) | `https://oderest.rsl.wustl.edu/live2` | Discover products, footprints, observation times, labels, and download URLs. Not an energy/mission simulation service. |

For the initial DE421 surface-geometry bundle, pin these files and store their hashes:

- [de421.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/a_old_versions/de421.bsp)
- [moon_pa_de421_1900-2050.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de421_1900-2050.bpc)
- [moon_080317.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf)
- [naif0012.tls](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls)
- [pck00011.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc)

Select `MOON_ME_DE421` explicitly. Respect each kernel's actual coverage. The binary lunar orientation file's approximate coverage is 1900–2050. LRO spacecraft kernels are needed for spacecraft/image reconstruction tasks, not simply for a stationary surface observer. [Frame specification](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf)

Horizons surface-observer example parameters:

```text
format=json
COMMAND='10'                 # Sun; use '399' for Earth
OBJ_DATA='NO'
EPHEM_TYPE='OBSERVER'
CENTER='coord@301'           # user coordinates on the Moon
COORD_TYPE='GEODETIC'
SITE_COORD='222.8,-89.44,0'   # east longitude deg, latitude deg, altitude km
START_TIME='2028-01-01'
STOP_TIME='2028-01-01 01:00'
STEP_SIZE='1 h'
QUANTITIES='4,13'            # azimuth/elevation and angular diameter
APPARENT='AIRLESS'
TIME_TYPE='UT'
CSV_FORMAT='YES'
```

Encode each value using a normal HTTP parameter encoder. The zero altitude is an illustrative reference-surface location, not the actual terrain height at these coordinates. Replace it with a verified altitude plus observer height. Parse service errors even when HTTP succeeds. JSON responses contain a textual `result` block that requires parsing. The prior sample query returned DE441 geometry; compare frames/conventions before comparing it to DE421 results. Apparent and geometric directions differ. [Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html)

For ODE, start with the valid instrument/product-type listing:

```text
https://oderest.rsl.wustl.edu/live2?query=iipt&odemetadb=moon&output=JSON
```

Then construct searches using the returned codes and documented bounding-box/product parameters. Store the original labels and actual download URLs. Use pagination, modest request rates, timeouts, retries, and local caches. [ODE manual](https://oderest.rsl.wustl.edu/ODE_REST_V2.1.6.pdf)

**3. Earth departure resources required in version one**

| ID | Resource | Obtain and build |
| --- | --- | --- |
| O01 | [NASA GMAT R2026a release](https://github.com/nasa/GMAT/releases/tag/R2026a) | Supported binary/source distribution and its required data files; verify installation/bindings on the selected development OS. |
| O02 | [Fixed-epoch lunar example](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_GivenEpochGoToTheMoon.script) | Reproduce unchanged first. Then parameterize a bounded epoch/orbit family and archive actual convergence and maneuver outputs. |
| O03 | [Lunar transfer/capture example](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_LunarTransfer.script) | Second regression case with its own initial state, force model and target conditions. |
| O04 | [GMAT script API guide](https://github.com/nasa/GMAT/blob/R2026a/doc/SystemDocs/Tools/source/API/source/userguide/ScriptUsage.rst) | Adapter around loading a trusted template, running it, and extracting runtime objects/summary. |
| O05 | [NASA Launch Services performance site](https://elvperf.ksc.nasa.gov/) | Optional public vehicle-performance context under its stated configurations and NASA-contract assumptions. Capture source/date/configuration for manually imported performance data. |

GMAT examples are executable reference problems, not solved data labels for every date. Their actual numerical outputs must be generated and checked. For each job, pin the script, gravity/ephemeris data, integrator, solver settings, and GMAT version. Do not silently give GMAT the surface SPICE bundle if its reference example requires different supporting data.

The public [LSP query interface](https://elvperf.ksc.nasa.gov/Pages/Query.aspx) offers circular, elliptical and high-energy queries. Its high-energy C3 range is -10 to 100 km²/s². The site describes mission/configuration-specific limitations; it does not supply booked launch dates or a public launch-availability API. LEO payload mass cannot be treated as translunar capacity. Version one should default vehicle compatibility to `not_assessed` unless a matching, sourced performance assessment exists.

A launch-pad catalog, if displayed, needs sourced coordinates and provider/configuration assumptions. It remains contextual until ascent and orbital-plane accessibility are modeled. There is no need to add a generic NASA image API or an unrelated space-news API to perform this project's calculations.

**4. Environmental and science extensions**

| ID | Source | Add when |
| --- | --- | --- |
| E01 | [NASA Lunar Surface Data Book, M2M-30044, March 2025](https://ntrs.nasa.gov/api/citations/20250002845/downloads/M2M-30044%20Lunar%20Surface%20Data%20Book%20Baseline_Final.pdf) | Immediately as the environmental reference and source index; it is not robot telemetry. |
| E02 | [Diviner archive](https://pds-geosciences.wustl.edu/missions/lro/diviner.htm), especially [polar cumulative products](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_pcp/) | Adding seasonal/diurnal thermal context or validating an explicit environmental thermal model. Product footprints/resolution must be preserved. It does not directly predict battery temperature. |
| E03 | [M³ Level-2 reflectance archive](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=CH1-ORB-L-M3-4-L2-REFLECTANCE-V1.0) | Adding mineralogical/hydration science targets. Reflectance/hydration is not a confirmed local extractable-ice inventory. |
| E04 | [ShadowCam archive](https://shadowcam.im-ldi.com/archive) | Adding imagery of shadowed terrain after confirming coverage/product suitability. Imagery alone does not supply height or traction labels. |
| E05 | [NASA POLAR Stereo](https://ti.arc.nasa.gov/dataset/IRG_PolarDB/) and [POLAR Traverse](https://ti.arc.nasa.gov/dataset/PolarTrav/) | Robot laboratory perception/localization extension. Images, calibration and LiDAR reference geometry do not calibrate lunar wheel–soil dynamics. |
| E06 | [RoSE mobility data](https://github.com/RoSE-Lab-Admin/Rover-Mobility-Dataset) | Robot laboratory mobility-model calibration on analog experiments; account for hardware, simulant and Earth gravity. Non-NASA source. |

**5. Inputs that come from the team or user**

The robot profile supplies battery, array, load and mobility parameters. The planner supplies required tasks, objectives, date ranges, search budgets, hard limits, permitted repairs, and assumed uncertainty distributions. Departure screening additionally needs the supported initial orbit, allowed orientation/maneuver variations, force model, target family, and capture-to-touchdown assumption.

Training labels for the mission surrogate are generated by the versioned simulator. Terrain is NASA-derived; the resulting battery/failure labels are simulated. Keep this distinction in manifests, exports, interface labels, and evaluation reports.

**6. Download and cache order**

1. D01 Site01 and one comparison region; inspect native coordinate/height conventions.
2. D02 regional context and G01 pinned geometry kernels.
3. D05 two observed/model reference scenes; D03 imagery/confidence as useful.
4. O01–O04 GMAT and both reference scripts; reproduce the unmodified cases.
5. E01 environmental reference and one declared robot profile.
6. D04 long-term comparison products, then feature-specific extensions.

Fetch catalog data during preparation. Run batch simulations from immutable local assets wherever practical. Cache keys must include source hashes, transformations, model versions and settings; a changed terrain or vehicle model must invalidate dependent results.
