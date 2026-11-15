# Battery thermal screening implementation

Status: implemented and optional in `/app/simulation`, 15 November 2026. Enable **Couple temperature and power**, then review **Properties** before running. The model identifier is `lumped-vacuum-battery-v0.1`; its request properties use `clavius-thermal-1`. Existing missions without thermal inputs keep the constant declared heater-load path.

The model treats the battery/enclosure as one spatially uniform thermal node. Inputs are effective heat capacity C, effective emission area εA, net effective solar absorption area αA, space view factor F, constant ground/space boundaries, conductance G, internal/conversion heat fractions, initial temperature, thermostat and charge/operating thresholds. NASA SPICE and the active measured terrain supply time/location, Sun direction, distance-scaled irradiance and terrain visibility. [NASA's thermal-control guide](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/) is a conceptual reference for the vacuum heat balance, not a lunar-temperature dataset or robot calibration.

## Heat and electrical balances

All heat equations use Kelvin, watts, seconds and joules internally. Celsius is the configuration/replay convention.

```
C dT/dt = Qsolar + Qbus + Qheater + Qconversion − Qradiation − Qconduction
Qsolar = (αA)net × incident irradiance
Qradiation = εA σ [F (T⁴ − Tspace⁴) + (1 − F) (T⁴ − Tground⁴)]
Qconduction = G (T − Tground)
σ = 5.670374419e−8 W m⁻² K⁻⁴
```

Incident irradiance includes the transformed body normal, finite-disk visibility and SPICE Sun distance. There is no convection. The effective solar area must describe heat remaining after electrical conversion; it is independent of panel rated output. The electrical scenario solar multiplier changes panel generation, not this independently declared absorption area. The user must reconcile these effective properties with the actual hardware's solar energy budget.

Thermostat demand uses the robot profile's heater wattage, with distinct on/off thresholds. Charging stops at the declared cold/hot thresholds and resumes inside the window by the specified hysteresis. Operating limits create timestamped violation events; these are declared thresholds, not measured cell chemistry. Capacity, voltage, efficiencies and discharge capability do not depend on temperature in this version.

The coupled integrator owns the **single chemical-energy ledger**. Available solar first serves loads; inhibited/full-battery surplus is curtailed. Charging/discharging applies the existing profile efficiencies. At zero battery energy, unmet demand is reported and delivered heater/electronics heat scales proportionally to the available electrical power. There is no invented heat from unpowered loads. This proportional allocation is a simplifying assumption, not a flight power-distribution controller. Route states after depletion remain counterfactual.

Environment forcing is held over the mission's existing 60 s/activity/visibility grid, with additional sampling at control transitions. RK4 uses the declared maximum step (default 1 s), a thermal stability bound and positive-Kelvin change bound. Bisection retains thermostat, BMS and operating-limit roots; full/empty battery boundaries are explicit. The integrator rejects excessive stiffness/transitions rather than silently loosening accuracy. A finer thermal step does not by itself refine the external terrain/illumination forcing.

Saved requests, source snapshots and evidence ZIPs retain all thermal properties, integration settings, model identity, heat integrals and energy residual. Replay shows continuous temperature, piecewise control states and the same elapsed clock used by energy/geometry. Saved legacy runs remain independent of a changed draft. Thermal properties currently belong to the mission request; the existing v0.1 robot capability contract has not been redefined.

## Validation and limits

The backend suite includes closed-form isolated-node, conductive and radiative cooling checks; thermostat root timing/cycling; cold charging inhibition and curtailed solar; zero-energy heater delivery; exact full/depleted battery boundaries (including negligible remnants); a limit touched while warming; 1 s/0.5 s integration convergence; a real-site coupled-energy reintegration; strict parameter validation and exported-source reproduction. These validate the implemented equations, not the hypothetical properties.

[Paired-run evidence](validation/thermal-screening.json) holds the 24 kg reference rover, 113.237 m route, 12 h duration and 2028-01-01 UTC epoch fixed. With the declared heater disabled, temperature crosses −10 °C at 16,548.499 s and ends at −40.299 °C, while 257.294 Wh remains. With thermostat heating enabled, temperature stays near 0–20 °C, heater delivery is 48.442 Wh, and final battery energy is 206.302 Wh. This demonstrates thermal/energy tradeoffs under these assumptions; it does not establish that this rover would behave that way on the Moon.

The browser acceptance run exercised property validation, a complete 12 h mission, a heater-event replay link, export and captured-source reproduction. The 187,170-byte ZIP reproduced all metrics within 1e−6 with no differences. Desktop 1440 × 900 and mobile 390 × 844 controls/replay were inspected; the property modal scrolls within the viewport. See the browser record in the validation JSON.

Two historical Diviner southern-summer local-time composites are now active as surface context. Their native records and gaps are documented in `NASA_DATASETS.md` and `DIVINER_CONTEXT.md`. A covered value may seed a constant ground scenario with an immutable source reference. It cannot be labeled an instantaneous 2028 boundary or battery measurement. Hardware measurements, multi-node/chassis coupling, time-dependent surface boundary, temperature-dependent battery behavior and observed lunar validation remain future work.

## Interface reference lock

Designing thermal scenario setup and linked temperature replay for robotics users in the existing Clavius web workspace. Direct build against the current Clavius design system. Refero's live catalog returned NO_SUBSCRIPTION on 15 November 2026; no live styles or screens were retrieved. The skill's bundled forms, typography and accessibility guidance is the fallback.

| Decision | Source | Role retained | Purpose |
| --- | --- | --- | --- |
| Add thermal setup beside mission assumptions; use an existing modal for detailed properties | Current mission/profile forms | Compact labels, SI units, modal validation | Keep parameter meaning visible without crowding the terrain |
| Keep the existing dark surfaces, Inter text and monospace metric values | Current Clavius workspace | Existing visual hierarchy | Match the working tool |
| Use green for the primary run action; use the existing muted blue for temperature and warning tone for limits | Existing power charts and reserve line | Action, measured/model series, constraint respectively | Avoid repurposing accent meanings |
| Add temperature to the shared replay clock and event links | Current replay/event workflow | One selected mission time | Explain the first thermal constraint crossing |
| Display explicit model/source scope beside thermal controls | Dataset continuity requirements | Engineering assumption disclosure | Prevent hypothetical properties or surface extrema from appearing measured |

Labels, focus states, validation errors and modal scrolling follow the bundled Refero craft guidance. The rendered controls and chart were checked on desktop and at 390 px width; the modal is vertically scrollable with no horizontal document overflow.
