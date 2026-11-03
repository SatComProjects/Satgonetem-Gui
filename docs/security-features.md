# Security and education features

Status: workstreams 1 (policy/QoS) and 2 (telemetry/detection/honeypot) are
implemented on `feat-SatSec`. The list of remaining gaps is at the end. This is
a living document and will be updated as later workstreams land.

Related material:

- [security-section.md](security-section.md) - lab design and classroom notes.
- [ideas.md](../ideas.md) - proposed labs and broader roadmap.
- [issue #21](https://github.com/SatComProjects/Satgonetem-Gui/issues/21) -
  roadmap tracking issue.

## Teaching model

The `/security` page is a guided range, not a collection of disconnected
buttons. Each unit starts with a short mission, exposes the live topology, and
ends with evidence that can be exported or observed:

- readiness strip: project loaded, containers running, addressing applied,
  routing applied;
- six working units: reconnaissance, DDoS, resilience, confidentiality,
  trust/spoofing, and policy/QoS;
- a seventh telemetry/alerts unit that shows the detection side;
- a bundled SatSec range with three ground stations, 24 satellites, and
  5000 Kbps links;
- a persistent safety banner and local-only assumptions.

The intended class loop is: **brief -> run -> observe -> defend -> write**.

## Implemented security features

| Feature | What students do | Evidence |
|---|---|---|
| Reconnaissance | Map links, capacities, delays, targets, interfaces, routes; write a target dossier | Exported Markdown dossier |
| DDoS | Run an iperf3 baseline, flood with hping3, compare throughput before/during/after | Throughput chart, job log, packet loss |
| Resilience | Fail an inter-satellite link, compare routes and recovery, reset the range | Route diff, failure/reset state |
| Confidentiality | Capture packets on an on-path satellite, download the pcap | `.pcap` with metadata and payload visibility |
| Trust / spoofing | Send SYN packets with a forged source, capture at the target | pcap evidence of the forged source |
| Policy / QoS | Apply default-deny, allowlists, BCP38, rate limits, connection limits, ingress policing, DSCP marking | Command preview, rule counters, rollback |
| Telemetry / alerts | Sample node/link counters, routes, protocol state, capacity; watch the alert timeline | Snapshot tables and alert history |
| Honeypot | Start a decoy SSH-like listener on a ground station, inspect connections | Connection events with timestamps and peers |

### Reconnaissance

The reconnaissance unit is a read-only target-dossier exercise:

1. Find the lowest-capacity links in a sorted table.
2. Click a link to inspect endpoints, capacity, delay, and state; add it to the
   evidence.
3. Pick an addressable target and inspect its loopback, interfaces, peers, and
   routing table.
4. Write why the target matters, the expected impact, and the likely path.
5. Export the dossier as Markdown.

### DDoS

The DDoS unit uses the existing traffic job registry:

- legitimate iperf3 flow;
- hping3 UDP, TCP SYN, or ICMP flood;
- rate mode: `--flood`, `--faster`, `--fast`, or explicit packets/sec;
- payload size, destination port, and TCP flags;
- attack and baseline durations with a Stop control.

The page starts the baseline, waits a lead-in, starts the attack, stops it, and
renders baseline/attack throughput from iperf3 intervals. If the original TCP
flow collapses before a mitigation lands, start a fresh baseline while the
policy is active.

### Resilience and confidentiality

- Link failure uses `simulate_link_failure()`; route tables before/after and a
  route diff make reconvergence visible.
- Reset restores the pre-lab project, restarts containers, and reapplies the
  routing method.
- tcpdump captures are bounded by packet count and duration. The pcap is read
  through the node channel, served as a download, and cleaned up by TTL.
- Captures on a satellite show the five-tuple, packet sizes, timing, and any
  plaintext payload; an encrypted overlay leaves only metadata.

### Trust / spoofing

The trust unit extends hping3 with `spoof_src`, `sport`, and `ttl`, validates
flags and IPv4 addresses, and optionally starts a capture before sending the
SYN. The evidence shows the forged source and the absence of a completed
handshake.

## Policy and QoS plane

The policy layer is server-side, not a GUI-only switch. It uses generated
`iptables`/`ip6tables` and `tc` commands with a saved ruleset for rollback.

Supported policy controls:

- default inbound accept/drop;
- established/related, loopback, and ICMP;
- management, TT&C, and telemetry allowlists by source CIDR, port, and protocol;
- BCP38 ingress rpfilter and explicit egress source CIDRs;
- per-source hashlimit rate limits, including SYN-only limits;
- per-source TCP connection limits;
- custom accept/drop/reject rules with rate-limited logging;
- ingress policing with a `tc` u32 police filter;
- DSCP marking in the mangle table.

API:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/security/policies` | Policies applied in this process |
| POST | `/api/security/policies/preview` | Dry-run command plan/diff |
| POST | `/api/security/policies` | Apply or replace a policy |
| GET | `/api/security/policies/{node}` | Chain status and rule counters |
| POST | `/api/security/policies/{node}/clear` | Restore the saved ruleset |

The DDoS panel can apply a source-specific rate/connection limit while the
attack is running. The probe used in development showed the rate-limit rule
dropping 44,315 packets / 1.24 MB from the attacker source.

Limitations:

- full egress per-flow class scheduling is deferred because SatGoNetEm owns the
  root qdisc; ingress policing and DSCP marking are implemented;
- `rpfilter` is IPv4-only in the current image;
- default-deny with no allowlists can make a node unreachable; the preview
  warns about this.

## Telemetry and detection

The telemetry adapter samples:

- per-interface RX/TX bytes, packets, drops, and errors from
  `/sys/class/net/*/statistics`;
- per-node route count and route hash;
- OSPF/IS-IS protocol-state lines from `birdc show protocols` when dynamic
  routing is active;
- TCP/UDP/ICMP counters from `/proc/net/snmp`;
- per-link capacity, delay, state, aggregated counters, and link-budget inputs;
- link budget frequency/bandwidth fields when configured.

The service derives rates from counter deltas and maintains baselines. Alerts
are generated for:

- route-table changes;
- routing protocol state changes;
- link state changes;
- interface drop/error deltas;
- link utilization above 90% of capacity;
- throughput spikes or drops against a rolling baseline;
- TCP RST, UDP, ICMP, and TCP retransmission packet-rate thresholds;
- honeypot connection events (shown separately in the UI).

The GUI renders a node table, link table, alert timeline, and a decoy honeypot
control. The telemetry page polls every 5 seconds while open.

`GET /api/security/telemetry/prometheus` exposes the latest interface/link
rates, capacity, and alert count as Prometheus text metrics.

What is intentionally not claimed:

- this is not Zeek/Suricata IDS; the Zeek/Suricata sidecar image remains a
  follow-up because it requires an image build and sidecar orchestration;
- C/N0 is not stored by the current link budget path; capacity and budget
  inputs are exposed, but a computed C/N0 field needs a link-budget service
  change;
- the detector is heuristic, not a production NIDS.

## Education features

- Mission checklists and target dossiers for reconnaissance.
- Guided attack parameters and observable results for DDoS, resilience,
  capture, and spoofing.
- Policy preview/diff, counters, and rollback for defense exercises.
- Alert timeline with severity, node, metric, and timestamp.
- Markdown dossier export.
- Bundled range preset and one-click range load.
- Readiness checks and error messages before labs start.
- Suggested class formats: 60-minute demo, 90-minute guided lab, 3-hour
  workshop, multi-week course.
- Opt-in real-container verification for policy, capture, link failure, reset,
  telemetry, and honeypot.

Not implemented yet: instructor mode, automated scoring, a capstone scenario,
and a full student/instructor split.

## API summary

| Area | Endpoints |
|---|---|
| Range | `GET /api/security/range`, `GET /api/security/preset` |
| Policy | `GET/POST /api/security/policies`, `POST /api/security/policies/preview`, `GET /api/security/policies/{node}`, `POST /api/security/policies/{node}/clear` |
| Telemetry | `GET /api/security/telemetry`, `GET /api/security/telemetry/prometheus`, `POST /api/security/telemetry/clear-alerts` |
| Honeypot | `POST /api/security/honeypots`, `GET /api/security/honeypots/{node}/{port}`, `POST /api/security/honeypots/{node}/{port}/stop` |
| Existing labs | `/api/security/links/...`, `/api/security/captures...`, `/api/traffic/...`, `/api/routing/...` |

All policy and honeypot endpoints require a loaded project; policy apply,
capture, telemetry, and honeypot actions require running containers.

## Requirements and safety

- Linux host with Docker and a running GoNetEm server.
- GoNetEm-launched containers are privileged; policy/honeypot operations use
  node command execution, not arbitrary user shell.
- The GUI binds loopback by default and has no authentication. Policy apply,
  clear, capture, and attack actions are trusted-local operations.
- Link failure and reset are destructive; reset rebuilds the project and
  restarts containers.
- Do not point hping3 or the firewall tools at real networks.
- The policy layer is not a production firewall manager; it is a teaching
  controller with explicit lab scope.

## Verification

Default suite:

```bash
uv run pytest
npm run test:js
npm run test:e2e
uv run ruff check .
```

Real-container path:

```bash
SATGONETEM_RUN_CONTAINER_TESTS=1 .venv/bin/pytest \
  tests/test_security_container_contract.py -s
```

The opt-in test covers policy apply/status/clear, telemetry sampling, honeypot
connection capture, link failure, pcap retrieval, reset, and post-reset state.

## Remaining roadmap

- `sgnt-monitor` sidecar with Zeek or Suricata and alert ingestion.
- Computed C/N0 and interference/noise-rise link-budget lab.
- True egress per-flow classes coordinated with the SatGoNetEm root qdisc.
- Scenario DSL, deterministic replay, and scoring.
- Instructor mode and capstone.
- GUI authentication/RBAC and audit logs.
- P4/BMv2 and HIL/SDR experiments.
