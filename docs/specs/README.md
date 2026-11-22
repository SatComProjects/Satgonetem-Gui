# Specifications

Write a specification before phased, multi-step, or public-contract work. It
records what will change, what "done" means, and how the change will be
verified. It does not replace tests; decisions with lasting tradeoffs belong in
an [ADR](../adr/README.md).

## Naming

- One topic per file: `NNNN-short-topic.md`, using the next free zero-padded
  number (for example `0001-design-principles.md`).
- Set the status when the work lands. Supersede an accepted specification with
  a new one instead of rewriting its history.

## Template

```markdown
# NNNN — Title

Status: draft

## Context

## Requirements

## Acceptance criteria

## Edge cases and error paths

## Non-goals

## Validation

## Decisions and open questions
```

## Related documents

- [Architecture decision records](../adr/README.md) capture decisions and
  their consequences.
- [Architecture and test baseline](../architecture.md) records the current
  structure and measurements.
- [Development guide](../../AGENTS.md) is the working agreement that governs
  every change.
