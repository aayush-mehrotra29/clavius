# Simulation site selection

15 November 2026. Extend the existing Clavius simulation workspace for engineers comparing measured lunar terrain. Keep the terrain, site/time form, NASA source detail, saved replay and comparisons consistent.

Reference lock: the existing Clavius simulation workspace and its native select controls, compact Inter typography, monospaced coordinates, green primary actions, blue charts and amber limits. The Refero catalogue previously returned `NO_SUBSCRIPTION`; bundled `refero-design/references/craft-details.md` supplies form-label and keyboard-focus guidance. No new visual system or decorative imagery is needed.

| Decision | Source and role | Reason |
| --- | --- | --- |
| Native labelled site select beside start time | Existing robot/layer controls; craft form labels | Keyboard operation and a clear selected value |
| Persistent map site name, coordinates, PGDA identity | User's geography/data provenance requirement | Distinguish two local ENU frames |
| Keep route offsets and activities on switch, explain in form | Existing editable route model | Predictable draft comparison; no implied safe route |
| Clear copied Diviner reference on site change | Source-specific ground-boundary contract | A previous site's observation cannot silently seed the new site |
| Loading overlay and disabled setup during terrain fetch | Existing loading and job controls | Prevent mixed-frame edits while the scene changes |
| Restore site before saved run rendering | Recorded mission provenance | Replay must display its own terrain |
| Site labels in saved history and a site row in comparisons | Existing comparison table | Expose the geography behind differing outcomes |

Browser QA must check both directions of site selection, true-height terrain replacement, saved Site04 replay, source labels, thermal context and the existing Connecting Ridge replay. Automated source and export tests complement visual verification.
