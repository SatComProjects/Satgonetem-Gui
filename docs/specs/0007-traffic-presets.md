# 0007 — Traffic presets, endpoint swap, clone, and replay

Status: accepted

## Context

The Traffic page builds one flow at a time, and the queue/history keep completed
runs. Repeating a flow requires re-entering every option, swapping endpoints has
no control, and neither the queue nor browser-local history can re-enqueue a
run. These are frontend-only gaps; the traffic API already accepts the payloads.

## Requirements

- Save the current traffic form as a named preset in browser-local storage
  (`sgnt_traffic_presets`), versioned, capped at 20, with case-insensitive
  upsert by name.
- Apply a preset to the form, including tool-specific fields; missing source or
  destination options must be reported rather than silently selecting another
  endpoint.
- Delete a saved preset and refresh the picker.
- Add a Swap endpoints control that exchanges source and destination.
- Add a Clone action to every queue item: a new queued item with a new ID, a
  deep-copied payload, a `(copy)` label, and no job ID/results; it must not
  start automatically.
- Add a Replay action to each history row: enqueue a new queued item from the
  recorded kind/payload/label with a `(replay)` label and delay 0.
- Persist presets defensively; malformed storage entries are dropped, not fatal.
- Keep the existing queue/history behavior and timers unchanged.

## Acceptance criteria

- Saving a preset adds it to the picker; reloading the page keeps it.
- Saving the same name with different casing replaces the existing preset
  instead of duplicating it.
- Applying a preset restores tool, endpoints, delay, and all visible
  tool-specific values; a missing endpoint produces a visible message.
- Delete removes the preset from storage and the picker.
- Swap exchanges the two selected endpoints in one action.
- Clone produces a second queue item with the same payload, a new ID, and
  `queued` status.
- Replay from history produces a queued item with the historical payload and
  `queued` status, without opening the results modal.
- Presets and queue items survive a reload through their storage keys.

## Edge cases and error paths

- Empty/whitespace preset names are rejected.
- Presets without source/destination or a known tool are discarded on load.
- Storage quota/write failures show a message and keep the in-memory list.
- Applying a preset after the project changed may leave absent endpoints
  unselected; the message names the missing endpoint.
- Clone/replay of a running item never copies the job ID or poll timer.
- Deleting a preset that is no longer in storage is a no-op with a message.
- The 20-preset cap discards the oldest entry on insert.

## Non-goals

- Server-side preset storage or sharing.
- Editing the traffic API payload schema.
- Auto-starting cloned/replayed items.
- Scheduled repeats or parameter sweeps.

## Validation

- Vitest for preset normalization/upsert/remove/caps and queue clone/replay
  freshness and payload isolation.
- Playwright for save/reload/apply/delete, endpoint swap, queue clone, and
  history replay with mocked traffic nodes.
- Full pytest (page/static contracts), Vitest, Playwright, Ruff, format, wheel
  build, and CI.

## Decisions and open questions

- Presets store the raw form fields rather than the API payload so tool-specific
  inputs round-trip exactly; the payload builder remains the single source of
  validation.
- Replay is exposed from history (the durable ledger) and clone from the queue;
  both use the same queue-item factory.
- Presets stay browser-local to match the interactive queue/history model.
