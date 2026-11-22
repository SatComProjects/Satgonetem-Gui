# 0001 — Project workspace/catalog

Status: accepted

## Context

The GUI can create projects and download a JSON backup, but it cannot list,
reopen, overwrite, duplicate, or delete projects under
`SATGONETEM_GUI_SAVE_ROOT`. Every restart requires a file picker, and there is
no safe server-side representation of the loaded project's save target.

The workspace must not become a path-traversal surface: clients must never send
an absolute or relative filesystem path that the server trusts. The workspace
is a local, trusted-user feature behind the existing loopback-only boundary.

## Requirements

- List project JSON files below the configured save root with an opaque ID,
  display name, filename, modified time, size, shell/satellite/station counts,
  and a validity flag.
- Open a listed project by opaque ID, using the existing validated load path and
  recording the file as the current session save target.
- Save the current project to a new workspace file with a user-supplied name;
  reject a collision unless `overwrite=true`; never write outside the save root.
- Save the current project in place when the session has a workspace target.
- Duplicate a listed project to a new filename without building it.
- Delete a listed project, refusing to delete the currently loaded file.
- Skip malformed/unreadable JSON with a visible warning rather than a 500.
- Use atomic writes and never expose absolute paths in API responses or URLs.

## Acceptance criteria

- `GET /api/projects` returns `{ok, projects, warnings}` and works without a
  loaded project.
- `POST /api/projects/{id}/load` loads by opaque ID and sets the save target.
- `POST /api/project/save-to` writes a new file, returns its opaque ID, and
  sets the session save target; repeat without overwrite is 409.
- `POST /api/project/save-in-place` overwrites the current workspace file or
  returns 409 when there is no target.
- `POST /api/projects/{id}/duplicate` and `DELETE /api/projects/{id}` work by
  opaque ID; deleting the current file is 409.
- Unknown/invalid IDs return 404; traversal-looking IDs never touch the
  filesystem.
- IDs are stable for the same relative path and never contain directory data.

## Edge cases and error paths

- Save root missing: listing returns an empty workspace; the first save creates
  the root if its parent is writable.
- Symlinks, hidden directories, `.tmp` files: skipped by the listing and never
  accepted as a target.
- Concurrent saves: atomic temp + replace; the last complete write wins.
- Project file deleted/changed between listing and load: 404 or normal load
  failure, never a traceback.
- Malformed JSON: skipped listing entry plus warning.
- Runtime-state projects without `simulation_property`: listed with unknown
  counts, still openable.
- Containers running: existing load guard remains 409 until stopped.
- Duplicate/delete name collisions: 409; delete confirmation is a UI concern.

## Non-goals

- Multi-user sharing, quotas, authentication, or remote storage.
- Editing project contents in the workspace before loading.
- Version control/history of workspace files.
- Persisting satellite addressability or other session-scoped state.

## Validation

- Storage unit tests for containment, IDs, listing, malformed files, atomic
  writes.
- Service/API tests for list/load/save-to/save-in-place/duplicate/delete and
  current-file protection.
- Playwright projects page list/open/duplicate/delete and save-current flows.
- `uv run pytest -q`, Vitest, Playwright, Ruff, format, wheel build.

## Decisions and open questions

- Opaque IDs are a SHA-256 prefix of the relative path; the server re-resolves
  them by scanning the contained file set.
- Duplicate is a file copy; it does not rewrite the project name inside the JSON.
- Should save-to update the in-memory project name? No; it changes the
  workspace file only.
