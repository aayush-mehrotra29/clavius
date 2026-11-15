# Two scientific simulation sites

Implemented 15 November 2026. Clavius now supports **Connecting Ridge (PGDA78 Site01)** and **Shackleton rim (PGDA78 Site04)** throughout terrain inspection, route/activity assessments, historical Diviner context, native dynamics, saved replay, comparisons, bounded repair searches and captured-source reproduction.

The global Moon explorer continues to use the 2019 Moon Kit. These two 5 m simulation packages are separate from the global display data.

## Sources and registration

The [NASA PGDA78 archive](https://pgda.gsfc.nasa.gov/products/78) supplies the Site04 surface, height-RMS raster and ROI archive. Original URLs, byte counts, SHA-256 identities, native CRS and the consulted NASA README are retained in `public/data/simulation-manifest.json`. The setup script verifies and prepares both sites. [Source checks](validation/multisite-sources.json) record the full asset identities and numerical checks.

Shackleton's analysis origin is the published `Site04_ROIs.dbf` record 4 X/Y anchor: −2,657.5 / −5,957.5 m in native south polar stereographic coordinates. Its inverse is 89.784873915° S, 204.040521234° E. It lies inside the fourth source polygon and at native pixel center column 1268 / row 1391. The projection residual is below 1 µm. Its source elevation is 1,737.228394 m above the 1,737.4 km sphere. The ±320 m local ENU patch ranges approximately −161.98 to +1.51 m relative to the local origin.

Five local-versus-regional height checks, at the anchor and source X/Y offsets of ±200 m, differ by at most 4.460449 m against the preset 30 m convention-check tolerance. This compares to a coarser 80 m surface; it does not establish absolute height or positional accuracy. Site01 retains its previous reference point and sub-2 m convention checks. Both sites use MOON_ME / DE421 and separate local ENU frames; they share the same regional PGDA90 raster cache.

The 5 m grids include interpolation between LOLA tracks. Their posting and our finer physics mesh do not establish independent measurement density, wheel-scale terrain, rocks, safe landing locations or calibrated soil response. Missing local and regional support fails explicitly.

## Site and context consistency

The site selector preserves the editable route offsets and required activities in the newly selected local frame, and invalidates the previous result. The map identifies the current site and PGDA source. Inspect the new terrain before interpreting the retained offsets as a traverse.

Each site has its own hash-pinned historical Diviner clip. Shackleton's 109,382-byte clip contains 386 midnight and 327 noon records; the original tables are shared with Site01. At the Shackleton origin the bins contain 181.582886 K (row 1,824,598) and 91.110558 K (row 1,644,797), respectively. They are historical summer/local-time composites, not a single day's temperature curve or ordered extrema. Applying a value declares a constant ground boundary. Switching site clears that reference and restores the declared default ground boundary; hardware properties remain in the draft. The API also rejects a reference from another site.

Saved history labels each site. Repair search replay first restores its source mission. Saved missions and dynamics restore their site before displaying terrain or replay. A linked probe must match its source mission's robot and site. Exports capture the site definition, local origin, exact terrain asset identities and any selected Diviner clip. Reproduction supplies the captured site catalogue independently of the currently displayed catalogue. Old Connecting Ridge requests without a site field retain their original default. The worker advertises explicit site-identity support; older workers cannot be selected silently.

## Executed evidence

All **83 backend tests**, **7 global-terrain tests**, and the production build passed. New tests use real Site04 data, native MuJoCo contact, distinct source identities, cross-site rejection, source-row checks and exported-source/context reproduction. Existing tests continue to cover the legacy Site01 workflow.

The [paired mission record](validation/multisite-acceptance.json) uses identical robot, UTC, 12 h duration, route offsets and required science activity at both sites. Site04 travels 113.2770 m, reaches 5.92694° maximum sampled terrain slope and ends at 155.9407 Wh. Site01 travels 113.2373 m, reaches 4.42942° and ends at 156.2409 Wh. These are conditional model results, not comparative real-world mission success estimates. The browser-created Site04 mission is `56d45cde-1221-473d-a756-505cabe75d88`; its 191,342-byte downloaded evidence ZIP [reproduces every metric](validation/shackleton-mission-reproduction.json) within relative/absolute 1e−6.

The rebuilt local Gazebo Harmonic 8.15.0 / DART / ROS 2 Jazzy worker passed its [native benchmark](validation/gazebo-native-benchmark.json). Its linked 20 s Shackleton probe (`798b8f8f-c871-4416-8605-df8172b0aee5`) drove 1.064595 m, emitted 201 received ROS clock messages and used 0.0676848 Wh in its independent physical ledger. The browser replay reached exactly 20 s and retained Site04. Its 292,538-byte downloaded export [reproduces every metric](validation/shackleton-gazebo-reproduction.json). Contact force/count channels remain null. [Runtime/image identity](validation/gazebo-multisite-runtime.json) is retained, as is the prior worker image tag `clavius-gazebo:source-03668ba63473`; switching runtime identities requires a matching benchmark.

A Site04 mission with usable-capacity multiplier 0.8 crossed its protected 75 Wh reserve at 42,505.86 s. A three-candidate capacity repair search retained the same robot, site, route and science activity, then froze two nominally supported candidates before three independent audits each. One candidate passed all three audits. The 1,251,782-byte search export [reproduces candidate outcomes and metrics](validation/shackleton-repair-reproduction.json). This searches within the selected site; automatic site and route alternatives remain separate unfinished work.

Desktop 1440 × 900 and mobile 390 × 844 browser checks cover site changes, saved-site restoration, terrain/layer replacement, source labels, thermal application/reset, native-engine selection, replay, evidence download and the comparison site row. The mobile context dialog scrolls vertically and the document has no horizontal overflow. See [browser evidence](validation/multisite-browser.json) and the [interface reference lock](MULTISITE_DESIGN.md).

The wider goal remains incomplete: full terrain ensembles/regional uncertainty, observed-shadow validation, calibrated wheel–soil/thermal response, broader repair alternatives and the retained orbital/GMAT handoff are not completed by adding a second site. See [the completion audit](COMPLETION_AUDIT.md).
