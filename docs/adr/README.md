# Architecture decision records

Record a decision here when it is costly to reverse, chooses between credible
alternatives, or changes a contract that other code and documentation depend
on. Routine implementation choices belong in the pull request or
specification instead.

## Naming

- One decision per file: `NNNN-short-topic.md`, using the next free
  zero-padded number.
- Status is `proposed`, `accepted`, `superseded by NNNN`, or `deprecated`.

## Template

```markdown
# NNNN — Title

Status: proposed

## Context

## Decision

## Consequences

## Alternatives considered
```

## Index

Add a link to each new record here.

- [0001 — Simulation transport controls](0001-simulation-transport.md)
- [0002 — Session-scoped satellite addressability](0002-session-scoped-addressability.md)

## Related documents

- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
- [Development guide](../../AGENTS.md)
