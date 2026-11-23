# 0012 — Scenario builder phase 1 (shells and ground stations)

Status: accepted

## Context

The Experiments page edits scenario YAML in a raw textarea. A Walker
constellation and ground stations are the common case, and hand-writing the
same YAML for every run is error-prone. SatGoNetem v0.3.2 provides a public
`Scenario` schema; the GUI can generate valid YAML from a structured form and
let the existing validation/run path handle the rest.

Phase 1 covers the experiment header, Walker shells, and ground stations.
Traffic, events, network overrides, and custom topology files remain in YAML.

## Requirements

- Add a collapsible "Scenario builder" section above the existing YAML editor.
- Form fields: name, duration, tick, routing, metrics interval, connectivity,
  plus dynamic Walker shell rows (identifier, planes, satellites per plane,
  inclination, revs per day, pattern) and ground-station rows (name, latitude,
  longitude, elevation).
- Generate YAML into the existing `#experiment-scenario` textarea without
  submitting or starting a run.
- Validate required names, at least one shell, numeric ranges, unique shell
  identifiers, and unique station names; show all errors in a visible message.
- Keep add/remove row logic and YAML generation in a pure
  `scenario_builder_model.js` with Vitest coverage.
- Start with one LEO shell and one Berlin ground station; add/remove controls
  must not drop valid data.
- Keep the existing run, detail, compare, and artifact flows unchanged.

## Acceptance criteria

- Opening the builder shows the default shell/station rows and seed values.
- Adding/removing a shell or station updates the rows and generated YAML.
- Generating with valid values replaces the textarea content with a
  deterministic YAML document; the existing run button can start it.
- Blank name, zero/negative shell counts, out-of-range latitude/longitude,
  non-positive duration/tick, duplicate shell identifiers, and duplicate
  station names produce a visible error and no textarea change.
- Strings are single-quoted safely (embedded quotes and newlines cannot break
  the YAML).
- Collapsing/opening the builder does not discard entered values.
- The generated YAML round-trips through the core `Scenario` parser in the
  backend test suite.

## Edge cases and error paths

- Removing the last shell or station is prevented with a message.
- Decimal values use a stable representation (no locale separators).
- Empty optional ground-station city/elevation falls back to a numeric 0.
- Very long names are bounded by input maxlength.
- Generated YAML never includes traffic/events; the section notes that these
  are edited in YAML.
- The builder does not run validation against the backend; the run path still
  validates and can return 422.

## Non-goals

- Traffic, event, network, TLE, or topology-file editing.
- Editing an arbitrary existing YAML document back into form fields.
- Running experiments directly from the builder.
- Replacing the raw YAML editor.

## Validation

- Vitest for defaults, add/remove, validation bounds/uniqueness, YAML quoting,
  and determinism.
- Backend test that generated YAML parses with the public `Scenario` parser.
- Playwright for open, add/remove, generate, error, and collapse behavior.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- YAML is generated rather than using the core `ScenarioDraft` serializer so
  the browser remains the only authoring path and no new API is needed.
- The form is intentionally phase 1; traffic/events are a later extension.
- Builder state is in memory only; it does not persist across reloads.
