# Clavius narrated application demo

Prepared 15 November 2026 for the Lunar Landing Site Navigator challenge. This script follows the current working application, including landing comparison, flight playback, rover replay and Mission analysis. Bracketed directions are for the presenter; read only the quoted narration. The supporting [requirements and dataset notes](DEMO_DATA_AND_REQUIREMENTS.md) contain sources and judge answers.

## Choose the recording format

The official Project Demo field accepts a video of **30 seconds or less**, or a deck of **up to seven slides including title and introductory slides**. Use the short script below for that field. The full walkthrough is a separate application showcase or local presentation where its length is permitted. The [2026 submission guide](https://www.spaceappschallenge.org/resources/project-submission-guide/) distinguishes the Project Demo from the final-project link; local presentation rules may differ.

## Official 30 second video

Aim for 27–29 seconds at a comfortable, rehearsed pace. Replace the two introduction placeholders, then time the final recording. Keep the screen footage moving beneath the narration; use a prepared comparison rather than waiting for computation.

| Time | Screen | Narration |
| --- | --- | --- |
| 0–4 s | Clavius title and team name | “I'm [name] from [team]. This is Clavius, our Lunar Landing Site Navigator.” |
| 4–9 s | Two sites and three dates in the comparison | “A landing delay changes sunlight and Earth visibility. Compare sites and dates together.” |
| 9–18 s | Scrub the horizon plot; show sunlight and Earth visibility bands | “NASA LOLA terrain and SPICE geometry show the local horizon, solar potential, and windows when Earth is visible.” |
| 18–25 s | Select an option, then cut to the matching rover replay | “Carry a selected scenario into a flight rehearsal and rover simulation, with recorded data and explicit assumptions.” |
| 25–29 s | Return to comparison; end on name and public project link | “Clavius makes lunar planning trade-offs easier to understand.” |

Use a small, readable overlay during the replay: **Planning prototype · hypothetical R1 rover · modeled conditions**. Leave the actual team name and final project link visible on the end frame. Keep credits in the project description and source panels; do not try to read dataset filenames in this cut.

## Full narrated walkthrough

Allow approximately 10–12 minutes including pointing, scrubbing and transitions. The optional lab tour adds approximately 4–6 minutes. Chapter times are editing targets, not computation deadlines. Precompute the landing comparison and a short successful traverse on the same local service used for recording.

### Opening and mission question

[Show the landing page briefly. Open **Get started** to reach `/app`.]

“This is Clavius, our application for the Lunar Landing Site Navigator challenge.

“Imagine that a lunar mission's landing date changes. The team needs to reconsider how much sunlight will reach its equipment, when Earth will be visible, and how those conditions differ between candidate sites.

“Clavius brings those comparisons into one workflow. We'll compare two south-polar sites, inspect their horizons, choose a scenario, and follow it into a flight rehearsal and a rover traverse. Throughout the demo, we'll keep the source data and model assumptions visible.”

### Compare landing sites and dates

[At **Plan your landing**, set first landing to **2028-01-21 12:00 UTC**, date spacing to **7 days**, and the surface window to **24 hours**. Start with **Balance sunlight and contact** and a **Level at the site** solar panel. These are demonstration inputs, not a mission recommendation. Open **Mission limits**, then run **Compare landing plans**. Cut past the processing wait.]

“We start with a landing date, a spacing between alternatives, and the length of time we want to evaluate on the surface.

“Clavius compares Connecting Ridge and Shackleton rim at three dates. That gives us six site-and-date options. For each one, it also evaluates three modeled transfer durations and retains the lowest required delta-v among the solved transfers.

“Our mission priority can favor solar energy, Earth visibility, or a lower transfer budget. The balanced setting compares both energy and visibility relative to the best eligible values in this search.

“We can also set limits on equivalent sunlight, the longest Earth outage, local slope, and transfer delta-v. Options outside those limits keep their explanations. The label ‘Best evaluated’ means best within this small comparison and its assumptions.”

[Select both sites at the same date, then another date at the same site. Point to the actual values. Do not claim a particular winner in advance. If no option meets the selected limits, show that result and explain the constraint before changing it.]

### Read the local sky and operational windows

[Point to **Local horizon**. Move **Time after touchdown**. Show the Sun and Earth markers, the changing readout, the next transition, and **Visibility windows · UTC**.]

“The most important view is the sky above the local terrain. The outline is the terrain horizon, and the markers show where the Sun and Earth are at the selected time.

“A body can be above the Moon's ideal spherical horizon and still be hidden by a ridge. Clavius combines local and regional elevation data to estimate that obstruction.

“As we move the timeline, we can inspect solar elevation, how much of the solar disk is visible, and whether Earth's center clears the terrain. The window bands make it easier to see when those conditions begin and end.

“Equivalent sunlight integrates the visible fraction of the Sun over time. Incident solar energy also accounts for the selected panel orientation. That energy is shown per square meter, before electrical conversion and equipment loads.

“Earth visibility is a geometric line-of-sight screen. Radio performance still depends on antennas, link margin and ground-station access. These windows are sampled estimates, so very short transitions can be missed.”

### Explain the NASA inputs

[Expand **Ranking and data**. Briefly show the source-hash link or saved planning data.]

“The surface calculations use NASA LOLA elevations at five-meter posting around each curated site, with an eighty-meter regional grid for more distant terrain. The Sun and Earth directions come from a pinned JPL SPICE and DE421 kernel bundle.

“Clavius preserves the source identities alongside its results. It also exposes height uncertainty and native-cell laser-return support, so the presence of a smooth surface does not imply that every part was directly measured.

“Five-meter posting supports this terrain-scale analysis. It does not resolve individual wheel-scale rocks or establish that a landing point is safe.”

### Follow the selected flight

[Choose an eligible option and click **Use this flight**. Open **Flight path**, orbit the scene, scrub the trajectory, and briefly switch to **Charts**.]

“Choosing an option opens its saved flight. The landing site and touchdown time stay linked to the comparison.

“The flight view shows Earth, the moving Moon, and the spacecraft trajectory on a shared clock. We can scrub the path or follow the spacecraft, then inspect velocity, Earth and Moon range, lunar altitude, and orbital energy in the charts.

“This is a simplified flight rehearsal from a two-hundred-kilometer Earth parking orbit. It uses two targeted point-mass coasts, an explicit correction, and a prescribed fifteen-minute descent. The descent reaches the surface by construction; vehicle thrust, fuel limits and landing dispersion remain unassessed.”

### Plan and simulate a rover traverse

[Click **Plan traverse**. Select **Clavius R1**. Toggle **Relief** and **Slope** on the map. Keep or enter a short route, such as E 2 m / N 0 m followed by E 4 m / N 0 m. Select **Science dwell**, **5 s**, and click **Simulate traverse**. Cut past the processing wait.]

“Next, we plan a short traverse at the same site and modeled touchdown time.

“The map combines historical LROC stereo imagery with relief and confidence-masked slope layers. We can place or edit waypoints, select the rover, and request a science dwell or a parked dwell at the destination.

“Here we're using Clavius R1, our hypothetical reference rover. Its mass, collision geometry and power profile are declared simulation inputs.

“The traverse runs native MuJoCo rigid-contact dynamics. A controller uses the rover's simulated position and heading to attempt the waypoints and final dwell. Solar generation uses the dated Sun direction, local horizon and recorded body attitude.

“The stereo map helps us inspect the route, while contact and picking use the nominal five-meter LOLA surface. A finer image or a smoother display does not increase the resolution of the physical terrain.”

### Replay and inspect mission analysis

[Let the rover replay begin. Show the requested route and traveled track, pause, scrub and change playback speed. Open **View mission analysis**.]

“The replay shows the saved motion, with the requested route and actual simulated track displayed separately. We can inspect the task outcome, distance, elapsed time, attitude and battery state.

“Mission analysis brings the planning decision and the rover run back together. It restores the matching landing-window horizon and comparison, so we can see why this scenario was selected.

“The route diagram shows which waypoints received arrival events. The telemetry cursor moves through battery energy, solar power, speed, roll and pitch, while marking the rover's position on the track.

“The flight budget separates the modeled maneuvers. The evidence panel exposes terrain and kernel hashes and links to the saved planning, flight and traverse data.

“If the rover does not finish, the app reports the unfinished task and keeps the run available to inspect. A successful simulated dwell is evidence about this declared case; hardware and soil calibration remain separate work.”

### Explore the global atlas

[Open `/app/atlas` from the workspace menu. Rotate the globe, filter **South pole**, search for a region and open its terrain view. Briefly show imagery, shaded relief, wireframe, grid and vertical exaggeration. Return to true scale.]

“Clavius also includes a global lunar atlas for geographic context. We can explore eight curated regions, search or filter them, or pin a location and read its coordinates and interpolated elevation. The URL preserves the selected region or pin and view mode.

“The atlas uses the 2019 NASA CGI Moon Kit. It displays an eight-thousand-pixel LROC mosaic, and the regional view streams the sixty-four-pixels-per-degree LOLA grid. Shaded relief, wireframe and illustrative lighting help explain the terrain.

“The atlas covers the globe, while the mission calculations are currently restricted to our two curated south-polar sites. Pinning an arbitrary point does not create a new supported simulation site.”

### Inspect the separate VIPER reference

[Open `/app/drive`. Show **Manual drive**, ordinary steering and **Crab steering**. Then select **Recorded dynamics**, switch between a straight and **25° crab traverse**, and open **Wheel slip & ground load**.]

“The rover-drive workspace adds a separate VIPER visual reference. Manual drive is interactive kinematics. Recorded dynamics plays native Project Chrono rigid-contact experiments, with wheel and suspension motion from the recorded body transforms.

“Each site has a twenty-second straight traverse and a twenty-five-degree crab traverse on nominal terrain, plus matching runs on terrain clone zero-zero-one. The wheel panel exposes simulated rolling slip, lateral motion and ground load.

“We keep these roles explicit. VIPER visualization and recorded component experiments do not replace R1 in the mission assessment, and they do not establish predictive VIPER flight performance.”

[Switch **Terrain surface** between nominal and clone 001. Open **Compare terrain surfaces**, then select **Sun at rover → Mission sunlight** and scrub one of the packaged dates.]

“Switching to the published statistical terrain realization lets us inspect how the same command responds to a different reconstruction. Contact, sunlight and parked-power inputs follow the selected surface.

“The dated-lighting view samples Sun visibility at the recorded rover positions. The same recorded drive can be examined under different dates, with a matching solar-array estimate. Its gross watts and generated watt-hours remain distinct from a complete battery budget.”

### Examine parked power

[Open **Parked power**. Choose nominal terrain, the Shackleton rim origin, **2028-01-21 12:00 UTC**, **48 h**, **90° heading**, **150 W load**, **75% starting charge**, and ideal charge/discharge efficiency. Use the actual labels and units in the dialog.]

“For a longer power question, we can hold the rover at a fixed position, choose its heading, electrical load and initial charge, and examine up to forty-eight hours.

“The reference capacity is five thousand four hundred twenty watt-hours at beginning of life and zero degrees Celsius. The load and efficiencies are scenario assumptions.

“In this documented nominal Shackleton case, demand first goes unmet at about thirty-four point four hours. Later sunlight restores some charge. That is why the first unmet load and the final battery value answer different questions.

“The same inputs at Connecting Ridge serve the load throughout this scenario. These results illustrate the effect of site-specific horizons under the model; actual battery endurance still needs electrical and thermal validation.”

### Close on the challenge

[Return to the landing comparison or Mission analysis. End with the public repository and final-project link.]

“Clavius helps planners explore alternatives when a date changes, and helps students see why the lunar horizon matters.

“NASA terrain and ephemerides drive the central comparison. The linked flight rehearsal, rover replay and evidence views make its consequences easier to inspect.

“The next development priorities are stronger observed-shadow validation, reconciled NASA robot mechanics, and calibrated wheel-soil and power models. Today's application provides a documented planning prototype whose assumptions remain attached to its results.”

## Optional simulation lab tour

Insert these chapters before the closing for a technical audience. They cover capabilities of `/app/simulation`, a separate workflow from the short native traverse at `/app`.

### Inspect and import a robot

[Open **Robot**, **Inspect 3D model & colliders**, **Mechanical inspection**, and **Capability profile**. If demonstrating import, use a prepared, valid URDF/ZIP and its profile.]

“The simulation lab exposes the robot model behind a run. We can inspect its links, joints, mass, center of mass, inertias and colliders, then review the separate mobility and power capability profile.

“The existing importer accepts a bounded family of wheeled URDF packages and checks their physical inputs and dependencies. Mechanical and capability edits create recorded versions. A visual mesh alone cannot supply missing mass, inertia or power properties.”

### Plan activities and compare assessments

[Open **Mission**. Show the site and surface selectors, UTC, observer height, route activities and constraints. Run or reopen a prepared mission. Scrub the shared timeline, select its events, then compare two compatible saved runs under **Runs**.]

“The lab assessment evaluates a route and scheduled activities over a longer surface window. It uses declared speed and power, accounts for uphill work and separate equipment loads, and checks battery reserve and Earth-outage limits.

“A shared clock links the scene, energy charts and constraint events. Saved-run comparison and bounded scenario sweeps expose how dates and declared capacity, generation or mobility assumptions change the outcome. The selected scenario set is visible.”

### Inspect terrain uncertainty

[Show **Terrain surface**, **Height RMS**, and **LOLA support**; inspect a native cell.]

“The lab loads nominal terrain and three published statistical realizations per site. Each complete alternative surface recomputes slopes, local horizons and contact in the same nominal coordinate frame.

“Height RMS and laser-return counts describe different aspects of the source. A zero count marks an interpolated nominal cell. Missing support remains unknown. Three realizations provide a limited sensitivity exercise, rather than the full hundred-member distribution or a calibrated risk probability.”

### Explain thermal screening and Diviner context

[Open **Battery temperature → Couple temperature and power**, inspect **Properties**, and open **Inspect NASA temperature context**.]

“Optional thermal screening couples a single battery-and-enclosure temperature node to the power ledger, including a thermostat and charging-temperature limits. Its hardware properties and constant ground boundary are explicit assumptions.

“Two Diviner southern-summer composites provide historical surface-temperature context at midnight and noon local time. They retain missing bins and site-specific provenance. A covered observation can seed a constant ground scenario, but it is neither a forecast for our mission date nor a battery measurement.”

### Run a detailed dynamics segment

[Select a saved mission cursor and open **Test rover dynamics**. Show MuJoCo and, only when ready, Gazebo / ROS 2.]

“A detailed probe starts from a selected mission position, heading and UTC. MuJoCo runs locally on the Mac. The separate Gazebo path uses Harmonic, DART and ROS 2 in the local Linux virtual machine, and requires its matching runtime benchmark.

“These are distinct rigid-contact engines with separate evidence. The detailed probe's energy record does not overwrite the lab mission ledger. Gazebo contact-force and contact-count channels remain unavailable.”

### Search alternatives and retain evidence

[Open a saved mission's **Find bounded alternatives**. Show date offsets, optional wait and permitted power changes, then open a completed search. Show preserved requirements, audited children and **Export evidence**.]

“The bounded alternative search preserves required tasks and hard limits while testing permitted schedule, wait and declared-power changes. It ranks candidates before testing a frozen selection against separate audit cases.

“An alternative is recommended only when every selected audit case supports it. The app retains the evaluated children, search budget and any unsearched candidates. Cancellation keeps completed work in a partial checkpoint.

“Evidence exports preserve inputs, source identities, recorded implementation and dependency pins for supported reproduction. These bounded checks help inspect assumptions; they do not establish a global optimum or a real-world success probability.”

### Inspect validation results

[Open **Data & models → Review wheel comparison & limits**, then the illumination and geometry evidence links.]

“Clavius reports failed validation targets alongside passing checks. The external JPL Horizons comparison checks geometric directions before terrain obstruction; observed-shadow comparisons test another part of the problem and still retain unresolved errors.

“The rigid wheel fixture misses the published NASA Glenn traction targets. A separate offline Chrono soil-model development campaign improves its held-out discrepancy but also fails its physical acceptance target. That model is not active lunar soil physics in the application.

“Keeping those results visible helps us identify what needs to improve before making stronger mission or hardware claims.”

## Recording preparation

1. Record the mission workflow on the local frontend and Python service. The current static hosting configuration does not provide a hosted computation backend. Use `npm run dev` after the documented environment and NASA cache setup; start the Gazebo worker only if its segment is part of the demonstration.
2. Keep one prepared six-option landing comparison and its selected flight and traverse on the same persistent service. Reopen their actual URLs before recording. A replay identifier alone will not transfer local runtime state to a public deployment.
3. Use short, tested waypoints. The main traverse accepts one to five points within ±12 m east/north, a 1–30 s final dwell, and a 180 s controller budget. Longer routes belong in the separate lab workflow.
4. Show the comparison before flight animation. Spend most of the first two minutes on site/date choices, the horizon and operational windows.
5. Record the displayed values. Avoid a prewritten claim that one site always wins. Keep nominal and clone results, UTC and lunar local time, watts and watt-hours, and incident Wh/m² distinct.
6. For mission sunlight, let the interface hide the historical photographic mosaic. Survey imagery and illustrative scene fill should not be described as photographs of the chosen future epoch.
7. Record required credits and SI/AI disclosures in the final materials. The submission guide requires visible identification of generated images/video, disclosure for generated audio, code and data, and restrictions on generated NASA branding. The landing sky/rockets are decorative generated artwork; the lunar data has separate provenance. This script was prepared with Codex assistance. Record other tool use according to what the team actually used.
8. Keep the official video within 30 seconds after titles and end frames are included. Check public access to both the Project Demo and final-project links. The project page remains the main submission record.

## Seven slide alternative

If the official demo uses slides instead of video, keep the complete deck within seven slides:

| Slide | Content | Visual |
| --- | --- | --- |
| 1 | Clavius, team members and selected challenge | Product identity and application screenshot |
| 2 | A landing delay changes sunlight and Earth visibility | One clear mission question |
| 3 | Compare two sites across three dates and inspect limits | Actual six-option comparison |
| 4 | Understand Sun and Earth against the terrain horizon | Horizon, timeline and visibility bands |
| 5 | NASA data drives the calculation | LOLA local/regional terrain, SPICE, and Horizons validation, with compact credits |
| 6 | Carry a selected scenario into a linked rehearsal | Flight, R1 traverse and analysis; label model assumptions |
| 7 | Audience value, validation limits, next steps and public links | Summary of the current prototype and evidence |
