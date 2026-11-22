# 0006 — Preflight diagnostics and honest build phases

Status: accepted

## Context

Project creation previously showed synthetic 10% and 30% progress values and
then waited for a 10-minute poll. A failed first run surfaced as a generic
request error, often after Docker, images, or storage problems that could have
been detected first. The GUI also had no estimate of how many containers a
configuration would create.

## Decision

1. Add `POST /api/diagnostics/preflight` with four bounded checks:
   - storage writability and at least 1 GiB free — **error**;
   - Docker daemon reachability — **warning**;
   - required images parsed from the bundled GoNetEm config — **warning**
     (or `unknown` when Docker is unreachable);
   - GoNetEm server TCP reachability — **warning**.
2. Treat only storage/configuration errors as blocking. A project can be built
   in-process without Docker; Docker and GoNetEm are required to run containers
   and traffic, so the UI warns without preventing a build.
3. Add a rough estimate from the submitted Walker shells and ground objects:
   satellite/ground counts, one container per node, and 128 MB per container.
   Label it explicitly as rough.
4. Replace synthetic creation percentages with lifecycle phases:
   `validating → building/loading → finalizing → ready|error`, plus elapsed
   time. Phases without a measurable percentage render an indeterminate bar
   instead of inventing one.
5. Keep responses successful (`ok=true`) when checks run but block; `blocking`
   is the semantic signal. This avoids colliding with the shared API error
   envelope, which reserves `ok=false` for failed requests.

## Consequences

- A preflight warning does not stop a build. The UI must distinguish warnings
  from blocking errors, which it does via `blocking` and check status.
- Docker/SDK/config probes are best-effort and bounded; an unavailable probe
  becomes a warning/unknown check, not a 500.
- Build phases are service-level boundaries, not a packet-level trace of the
  core build. The elapsed time and phase label are honest; the indeterminate
  bar does not claim a percentage.
- The estimate can undercount stations supplied via a `data_file`; the response
  includes an explicit warning.
- Adding the preflight adapter makes `docker` and `pyyaml` direct dependencies.

## Alternatives considered

- **Block creation when Docker is unavailable.** Rejected: the build itself is
  in-process and can succeed; blocking would prevent offline topology design.
- **Keep synthetic percentages.** Rejected: it misrepresents uncertain work.
- **Instrument every adapter phase.** Deferred: the core build is one call; the
  service-level phases are accurate and much less invasive.
- **Use the Docker CLI instead of the SDK.** Rejected: the SDK is already a core
  dependency and gives bounded timeouts without shell parsing.
- **Estimate memory from the actual image.** Deferred: image metadata is not a
  reliable runtime-memory predictor; 128 MB is a documented rough assumption.

## Related documents

- [0005 — Link metrics scope and deferred utilization](0005-link-metrics-scope.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
