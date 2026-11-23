# 0010 — Responsive shell, accessible navigation, and keyboard shortcuts

Status: accepted

## Context

The shared header now carries nine navigation links with no wrap strategy or
active state, the floating queue is a fixed 360 px panel, and World View keeps
a large inline stylesheet. Keyboard users cannot discover or use common
navigations, and there is no skip link to the main content.

## Requirements

- Add a skip link and a `<main id="main-content">` landmark around page content.
- Mark the current page in the header with `aria-current="page"` and a visible
  active style.
- Make the header/nav wrap cleanly on narrow screens and provide responsive
  queue behavior instead of a fixed 360 px panel.
- Move World View's inline CSS into `/static/world.css` without changing
  rendering.
- Add global focus-visible styling for links, buttons, inputs, selects, and
  textareas.
- Add keyboard shortcuts with editable-target and modifier guards:
  - `?` opens a shortcuts help dialog;
  - `g` followed by `d`, `w`, `n`, or `t` navigates to Dashboard, World View,
    Nodes, or Traffic;
  - `Escape` closes the help dialog;
  - shortcuts never fire while typing in an input, textarea, select, or
    contenteditable element, or with Ctrl/Meta/Alt held.
- Add a visible `?` help button to the header.
- Keep pure shortcut metadata/guards in `shortcuts_model.js` with Vitest tests.

## Acceptance criteria

- Each page's nav link has `aria-current="page"` and an active visual state.
- The skip link becomes visible on focus and targets the main landmark.
- Pressing `?` on a page body opens a modal help dialog listing the shortcuts;
  Escape closes it and focus returns to the opener.
- `g` then `d/w/n/t` navigates to the corresponding page; a lone `g` expires
  after a short timeout.
- Typing `?` in an input does not open the dialog; Ctrl/Meta/Alt combinations
  are ignored.
- The queue remains usable at 390 px wide (full-width bottom sheet rather than
  a clipped 360 px panel).
- World View renders the same controls after its CSS moves to `world.css`.
- Existing modal focus traps, path controls, queue behavior, and page tests
  continue to pass.

## Edge cases and error paths

- A shortcut pressed while the results modal is open must not navigate behind
  the modal.
- The help dialog traps focus and restores the previously focused element.
- Unknown `g` prefixes are ignored and clear the prefix.
- Repeated rapid `g` presses do not stack navigation.
- The help button is keyboard reachable and labelled.
- World CSS move must preserve every selector, including fullscreen rules and
  responsive breakpoints.

## Non-goals

- Per-page shortcut customization or a command palette.
- Replacing native browser navigation.
- Screen-reader certification; a manual spot check is reported.
- Redesigning page layouts beyond shared shell/queue responsiveness.

## Validation

- Vitest for editable/modifier guards, `g` prefix resolution, and the shortcut
  catalogue.
- Playwright for `?`/Escape, `g` navigation, editable-target suppression, the
  active nav state, and the skip link.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.
- Manual checks: real screen-reader spot check, projector/tablet layout, and
  the World View 3D page after the CSS move.

## Decisions and open questions

- Navigation shortcuts use a `g` prefix so single letters remain available to
  page controls.
- The help dialog uses native `<dialog>` semantics and the existing modal
  styling patterns.
- The World CSS move is mechanical; any visual drift is treated as a
  regression and fixed before merge.
