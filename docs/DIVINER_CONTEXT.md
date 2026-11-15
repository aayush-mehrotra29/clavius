# Historical Diviner surface context

Implemented 15 November 2026. This adds two native 240 m southern-summer bolometric brightness-temperature composites to the Connecting Ridge and Shackleton rim workspaces. The interval is 5 July 2009–17 February 2019, with local-time bins 00:00–00:15 and 12:00–12:15. The exact PDS product IDs, URLs, source/label hashes and clip hash are under `diviner` in `public/data/simulation-manifest.json`.

The first waypoint is queried in lunar planetocentric coordinates. Only an observed native bin containing that point is returned. No point is filled from a distant neighbor, another local-time bin or a mission-date estimate. A conservative 2 m border inside the nominal half-cell width is treated as ambiguous. The 5 km prepared clip has an additional native-cell-width outer guard. Posting is not guaranteed position or temperature accuracy.

The source labels describe normalized stereographic x/y but attach `deg` units in PDS4. Clavius uses explicit center latitude/longitude for conversion, then independently checks the normalized source x/y multiplied by 1,737,400 m. Across 6,949,510 table records the maximum valid-coordinate residual is 0.015491 m, below the predeclared 0.1 m conversion tolerance. This is a coordinate-format check, not external geolocation validation. The clip retains 437 midnight and 149 noon native records, without interpolation.

At the Connecting Ridge origin, midnight contains 148.724106 K from source table row 1,751,157. The noon bin has a gap; its closest observed record is not substituted. These two bins are neither daily extrema nor a full diurnal curve. Per-bin measurement counts/error bars are not included in these source tables. Bolometric brightness temperature is not an in-situ soil or battery temperature.

Users can copy a covered value to the thermal model's **constant ground boundary**. This enables the model and explicitly assumes one temperature across the route and duration. The model retains the product, table row, exact value, source hashes and clip identity; editing the ground value clears its NASA reference. The API rejects a changed value that retains a mismatched reference. Hardware thermal properties remain engineering assumptions. No instantaneous future surface or battery observation is implied.

## Preparation and evidence

```
.venv/bin/python scripts/setup_simulation.py --diviner
.venv/bin/python scripts/prepare_diviner_context.py
```

The optional source tables total 410,021,208 bytes; six table/label files are retained under ignored `data/raw/diviner/`. Preparation verifies pinned hashes and label record lengths/counts, respects special constants and recreates the exact 91,221-byte Connecting Ridge and 109,382-byte Shackleton rim context clips. Ordinary simulation setup does not require this optional download.

Referenced mission exports include the immutable clip and manifest alongside the captured implementation and robot. Reproduction uses those captured context files, verifies their identity and the source cache, and does not require the current display clip to stay unchanged. Raw tables are not placed in every evidence ZIP.

## Interface reference lock

Designing a scientific context picker for the existing Clavius web workspace. Direct build uses its thermal property modal, source disclosures, monospace numerical values, native buttons, labels and focus states. The earlier Refero catalog attempts returned NO_SUBSCRIPTION, so its bundled craft guidance and the existing product are the available references. No new visual system or raster illustration is needed.

| Decision | Reference | Purpose |
| --- | --- | --- |
| Context inspection is an explicit button beside thermal setup | Existing Data & models and property inspection actions | Keep measured context separate from editable model properties |
| Show value, Kelvin/Celsius, local-time/season and coverage together | Existing source inspector and engineering unit labels | Explain what each historical value represents |
| Missing bin has explanatory text and no apply action | Existing unsupported-data states; dataset continuity rules | Preserve actual observational coverage |
| Apply action states that it creates a constant boundary | Existing explicit scenario controls | Make the modeling assumption reviewable before use |
| Use the same scrollable modal at 390 px | Existing profile/thermal form | Keep values and primary action reachable |

Desktop 1440 × 900 and mobile 390 × 844 context controls were checked. The mobile dialog is 358 px wide, scrolls vertically, and causes no horizontal document overflow. Copying a value enables thermal screening; editing it clears the NASA reference. A full referenced mission/export/reproduction acceptance check is recorded in `docs/validation/diviner-context.json`. Scientific tests validate ingestion, reference identity, coverage gaps and reproduction; they do not establish a thermal hardware calibration.

The browser-created 12 h scenario (`bd4a989a-1d34-4cdf-b4ca-1d8d9d5006e7`) retained the native midnight row and used 39.999583 Wh of heater energy, ending at 215.188719 Wh. Its 214,245-byte evidence ZIP includes the 91,221-byte context clip and full source manifest. Captured-source/context reproduction passed for every metric with relative/absolute tolerance 1e−6 and no differences. This is a conditional constant-boundary scenario, not a thermal forecast.

Shackleton rim uses a separate 5 km clip with 386 midnight and 327 noon records. At its analysis origin the values are 181.582886 K (midnight, row 1,824,598) and 91.110558 K (noon, row 1,644,797). Historical composites are not a single-day curve or ordered extrema. The site picker clears a copied ground reference on change; the API also rejects references from another site. Exports name the captured clip by site and reproduction pins it independently of the active catalogue. See [multi-site evidence](MULTISITE.md).
