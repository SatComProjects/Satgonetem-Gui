# 0011 — Link-budget workbench (calculator)

Status: accepted

## Context

SatGoNetem v0.3.2 exposes a public RF link-budget chain (antennas, EIRP,
free-space and atmospheric loss, C/N₀, C/N, Shannon/MODCOD capacity). The GUI
only exposes two static capacity numbers (ISL/G-S) and cannot explain where a
capacity comes from.

Phase 1 is a standalone what-if workbench: enter geometry and RF parameters,
get the full downlink or uplink budget and capacity. Applying the budget to a
project's GSLs and persisting it belongs to a later phase because it changes the
project document and needs an ADR.

## Requirements

- Add `POST /api/analysis/link-budget` that works without a loaded project.
- Accept downlink/uplink direction, frequency, bandwidth, slant distance,
  elevation, ground-station coordinates, satellite and ground antenna
  diameter/efficiency/EIRP/losses, receiver system temperature, unavailability,
  and a Shannon or MODCOD capacity strategy.
- Return capacity (kbps and Mbps), EIRP, G/T, free-space loss, atmospheric
  attenuation, C/N₀, C/N, and whether the atmospheric model was available.
- Use the public core `AntennaConfig`, `Antenna`, `LinkBudgetInputs`,
  `LinkBudgetService`, `ShannonCapacityStrategy`, `ModCodCapacityStrategy`,
  `calculate_free_space_loss_db`,
  `calculate_carrier_to_noise_power_spectral_density_ratio`,
  `calculate_carrier_to_noise_ratio`, and
  `calculate_atmospheric_attenuation_dB`.
- Validate all numeric bounds in Pydantic; invalid inputs are 422.
- If the optional atmospheric model raises, fall back to 0 dB and report
  `atmospheric_available: false` instead of failing.
- Add a `/link-budget` page with grouped inputs, a capacity hero, a breakdown,
  and loading/error states.
- Keep pure formatting/summary logic in `link_budget_model.js`.

## Acceptance criteria

- A valid default downlink request returns finite EIRP, G/T, FSPL, C/N₀, C/N,
  and a non-negative capacity; the response echoes direction/frequency/
  bandwidth/distance/elevation/strategy.
- Increasing receiver noise temperature lowers capacity; increasing the
  receiver antenna diameter increases capacity; increasing distance lowers
  C/N₀.
- MODCOD and Shannon strategies both return a capacity, and the strategy is
  echoed.
- Uplink swaps the transmit/receive antenna roles while keeping the ground
  antenna diameter for the rain model.
- Invalid frequency, bandwidth, distance, elevation, antenna, or efficiency
  bounds are 422 with the common error envelope.
- The page renders the capacity, breakdown, strategy/direction labels, and an
  error message for a 422.
- The endpoint is registered as a blocking route and appears in OpenAPI.

## Edge cases and error paths

- A zero-capacity result is still returned with its breakdown, not an error.
- `satellite_eirp_db`/`ground_eirp_db` override the computed EIRP when supplied.
- Negative or zero loss inputs are rejected; efficiency is capped at 1.
- Atmospheric failure is reported, not swallowed silently.
- Form values are bounded by the same limits as the schema.
- Units are labelled in the UI (GHz, MHz, km, m, dB, K, %).

## Non-goals

- Applying the budget to project GSL capacities or saving it in project JSON
  (phase 2, needs an ADR and save/load contract).
- Uplink/downlink pair optimisation or rain-zone maps.
- Real RF validation against hardware.
- TLE or orbital propagation.

## Validation

- Adapter tests with the real core chain for sensible values, monotonic
  comparisons, strategy differences, and atmospheric fallback.
- API tests for success, bounds, no-project independence, and the blocking
  route contract.
- Vitest for dB/capacity formatting and summaries.
- Playwright for the calculate flow and a 422 error.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- Phase 1 is deliberately read-only: it answers "what capacity would this RF
  chain produce?" without mutating a project.
- The calculator uses the core service for capacity and the public helpers for
  the breakdown, so displayed values match the model chain.
- Atmospheric attenuation may require the optional `itur` dependency; the
  fallback keeps the workbench usable.
