# Security section: teaching cybersecurity in space with SatGoNetEm

Status: implemented on `feat-SatSec`; tracking issue
[#10](https://github.com/SatComProjects/Satgonetem-Gui/issues/10) with phase
sub-issues [#15](https://github.com/SatComProjects/Satgonetem-Gui/issues/15)
through [#20](https://github.com/SatComProjects/Satgonetem-Gui/issues/20).

## Implementation status

| Unit | Code |
|---|---|
| Reconnaissance | `/security` page, readiness strip, link inventory (`links.py`, `satgonetem_topology.py`) |
| DDoS | `static/security.js` + `static/security_model.js` over the existing traffic jobs |
| Resilience | `SecurityService.fail_link/reset`, `SatGoNetemSecurityAdapter.fail_link`, route diff in the page |
| Confidentiality | `SecurityService` capture lifecycle, `SatGoNetemSecurityAdapter` tcpdump/base64 path, capture download route |
| Trust / spoofing | `Hping3Request` spoof fields, traffic adapter pass-through, trust panel capture evidence |
| Policy & QoS | `PolicyService`, `SatGoNetemPolicyAdapter`, `/api/security/policies`, policy panel in `security.html` |

The five labs require a running GoNetEm network for capture, link failure, and
traffic actions. The policy workstream adds typed firewall/QoS apply, preview,
status, counters, and rollback. The default test suite uses fakes; the
real-container path is documented as an opt-in verification. The tabletop and
capstone units remain out of scope for this implementation.

## Purpose

Add a `/security` section to the GUI that turns the emulator into a small
teaching range for satellite cybersecurity. The section is not a second traffic
page: it is a guided sequence of briefings, live exercises, observations, and
debriefs. Each exercise should end with an observable effect in the emulator and
a defensible answer to "what would a defender do?"

The intended audience is a class with no assumed satellite-security background.
Students should already know basic IP networking (addresses, routes, TCP/UDP,
packet loss, throughput).

## Design rules

1. **Demonstrate, do not simulate with slides.** If a claim can be shown in the
   emulator, run it. If it cannot, say so and use a tabletop exercise.
2. **Use SatGoNetEm primitives, not a parallel toolchain.** Traffic, links,
   routes, and captures should go through the existing services and adapters.
3. **Never expose arbitrary shell execution in the web UI.** Lab actions are
   allowlisted and parameterised. The GUI has no authentication and is meant
   for trusted local use.
4. **Every attack has a measurement and a debrief.** Throughput, loss, RTT,
   route change, or captured packets. "It looked slow" is not evidence.
5. **Reset must be one click.** Several exercises mutate the topology.

## What SatGoNetEm already provides

The emulator is a good fit for a network-security lab because it runs real
Linux protocol stacks in containers rather than abstracting packets away.

| Primitive | Teaching use | Status in this GUI |
|---|---|---|
| `hping3` with TCP/UDP/ICMP, flags, rate modes, spoofed source | Attack traffic: SYN/UDP/ICMP floods, crafted packets, source spoofing | Partly exposed on `/traffic`: the page has proto, port, count, size, and rate, but no flag or spoof controls; the request model has `flags` but lacks `spoof_src`, `sport`, and `ttl` |
| `iperf3` TCP/UDP | Baseline and impact measurement: throughput, retransmits, loss, jitter | Exposed on `/traffic` |
| `ping` | Reachability, RTT, loss before/after an event | Exposed on `/traffic` |
| `tcpdump` on satellite interfaces | Eavesdropping, packet-level evidence, detection | Not exposed in the GUI |
| `simulate_link_failure()` | Link loss, route reconvergence, resilience comparison | Not exposed in the GUI |
| Static/Dijkstra, OSPF, IS-IS, SR-MPLS | Compare resilience and control-plane behaviour | Exposed on the dashboard |
| Link capacity and delay (`tc netem`/TBF) | Bottlenecks, saturation, jamming analogue via loss/jitter | Capacity is used at build time but not shown in the API |
| Docker node images | Separate space and ground nodes with real network stacks | Already the execution model |
| Hardware-in-the-loop | Real ground equipment, SDR, or RF hardware | Supported upstream, not used by this GUI |

The SatGoNetEm paper explicitly lists `hping3` "for attack simulation" and
`tcpdump` "for packet-level analysis" in the satellite image, so units 2 and 4
below use capabilities the platform was designed to support.

## Curriculum

The section has eight units: unit 0 is a lecture, units 1-5 are live exercises,
unit 6 is a tabletop, and unit 7 is a live capstone. The tabletop exists because
the emulator does not model firmware or radio frequency.

| Unit | Mode | Central question | Live artefact |
|---|---|---|---|
| 0. Threat model | Lecture | What is different about security in space? | Threat-model canvas |
| 1. Reconnaissance | Live | What can an attacker learn before touching the system? | Ranked target list |
| 2. Availability | Live | How little traffic does it take to starve a satellite link? | Baseline vs attack throughput chart |
| 3. Resilience | Live | What happens when a link disappears, and how fast does routing recover? | Loss timeline and route diff |
| 4. Confidentiality | Live | What does an on-path satellite see? | Downloaded packet capture |
| 5. Integrity and trust | Live | Why is a source address not an identity? | Spoofed packets at the target |
| 6. Ground segment and supply chain | Tabletop | How does a compromised ground station reach orbit? | Attack-path diagram and controls |
| 7. Capstone | Live | Can a blue team detect and contain a red team? | Incident report |

### Unit 0 - Threat model (20 min, lecture)

Cover the parts that the emulator cannot show, so students know the boundaries
of the lab:

- Segments: space, ground, user, and the control/TT&C path. Trust boundaries
  between them are often weaker than the diagram suggests.
- Space-specific constraints: predictable passes and public orbital data,
  intermittent connectivity, long propagation delay, constrained onboard
  resources, shared spectrum, physical access, and a long supply chain.
- Goals: confidentiality, integrity, availability, and safety. A satellite
  outage is not only a data-loss event.
- Threat actors: from an amateur with an SDR or a Ground-Station-as-a-Service
  account to an insider or a state actor.
- Real incidents: Viasat KA-SAT/AcidRain (2022), the Dozor compromise, the
  ICARUS DDoS research on LEO constellations, the "Space Odyssey" firmware
  analysis, and GNSS jamming/spoofing.
- Exercise: fill a threat-model canvas for the constellation the class will use.
  Identify assets, entry points, and the three most plausible attack paths.

The instructor should say explicitly which later units demonstrate which threat,
and which are only discussed.

### Unit 1 - Reconnaissance and attack surface (30 min, live)

Students load a range preset and enumerate it without sending attack traffic.
The page presents a short mission and a target dossier so the exercise has a
concrete deliverable.

1. Scan the sorted link table and identify the lowest-capacity links. Those are
   the bottleneck candidates.
2. Click a link row to inspect its endpoints, capacity, delay, and state, then
   add it to the evidence field.
3. Choose an addressable target and inspect its loopback, interfaces, peer
   names, and routing table in the target dossier.
4. Write the target card: why this target, what the attacker gains, and which
   path or link the attack would use.
5. Export the dossier as Markdown for the lab report.

Discuss what is public in real life: TLEs, ground-station coordinates,
frequency allocations, link budgets, and vendor documentation.

Deliverable: a target dossier with a bottleneck link, a chosen target, its
interfaces/routes, and a justified expected impact. No attack yet, so the range
stays clean for unit 2.

### Unit 2 - Availability: saturating an inter-satellite link (45 min, live)

This is the strongest lab because every ingredient already exists.

Setup: the bundled range has three ground stations, 24 satellites, and
deliberately low-capacity links (5000 Kbps). Static routing first, so the path is
stable.

1. Run a baseline `iperf3` TCP flow between two ground stations for 15-20 s.
   Record average throughput, retransmits, and RTT.
2. Launch an `hping3` UDP, TCP-SYN, or ICMP flood from an "attacker" ground
   station or a compromised node toward the victim ground station, or toward an
   addressable satellite on the path. Start with one attacker, then two or three.
3. Vary the attack: protocol, rate mode (`--fast`, `--faster`, `--flood`, or an
   explicit packets/sec interval), packet payload size, destination port, and
   TCP flags. Keep the other variables fixed so the class can attribute the
   change.
4. Keep the legitimate flow running. Observe throughput collapse, packet loss,
   RTT growth, and the job queue's charts.
5. Repeat with a higher-capacity link, a different target, and a different
   routing method. Ask students which variable changed the outcome.
6. Debrief: why a small amount of traffic can starve a shared link, why the
   attack is cheap, what collateral damage looks like, and how a defender would
   notice it. Connect to the ICARUS result.

Defences to discuss: capacity planning, traffic policing and rate limits,
admission control, rerouting, scrubbing, and baseline-based monitoring. A
rate-limit control would let students test a mitigation instead of only
discussing it.

The security page exposes the attack controls directly: protocol, rate mode
(fast/faster/flood or packets/sec), packet payload size, destination port, TCP
flags, attack duration, and baseline duration. The runner starts the baseline,
starts the attack after a short lead-in, stops the attack, and renders the
before/after chart from the existing traffic job registry and Chart.js.

### Unit 3 - Resilience: link failure and routing recovery (40 min, live)

Students see the difference between "the link is down" and "the network has
recovered".

1. Establish a baseline `ping` and `iperf3` between two ground stations.
2. Fail one inter-satellite or ground-station link with
   `simulate_link_failure()`.
3. Measure the immediate loss, then wait for reconvergence and measure again.
4. Repeat under static routing, OSPF, and IS-IS. Compare outage duration and the
   path after recovery. A route diff makes the change visible.
5. Discuss physical threats (jamming, debris, kinetic effects) and
   control-plane threats (route poisoning, blackholing, adjacency attacks).
   Emphasise that dynamic routing improves resilience but adds a trust problem:
   who is allowed to announce a route?

GUI work: a link inventory with a "fail this link" action, a route-diff view,
and a reset button. `simulate_link_failure()` removes links from the simulation
manager and is not reversed by a "restore" call, so reset needs a project
snapshot/reload or a rebuild. A safer classroom variant is reversible
impairment: inject packet loss and jitter through the link's netem parameters,
then set them back to zero. That demonstrates an interference analogue without
destroying the topology; label it as a packet-level analogue, not RF jamming.

### Unit 4 - Confidentiality: listening on an on-path satellite (40 min, live)

The emulator runs real `tcpdump` in the satellite image, which makes the
"encrypt the link" lesson concrete.

1. Start a plaintext application flow between two ground stations (an `iperf3`
   flow is enough to show metadata; a small HTTP or telemetry exchange is better
   if the image has the tools).
2. Start a capture on a satellite that carries the flow, limited by packet
   count and duration. Stop it and download the `.pcap`.
3. Open the capture in Wireshark: show the five-tuple, packet sizes, timing, and
   whatever payload is visible. Ask what an operator could infer from metadata
   alone.
4. Repeat with an encrypted flow (TLS, SSH, or an encrypted overlay) if the
   image supports it. The metadata remains; the payload does not.
5. Discuss link-layer encryption, key management, forward secrecy, ground
   station trust, and why encrypting only at the gateway is insufficient.

GUI work: start/stop capture on a selected node, cap packets and bytes, list
captures, and serve them as downloads from a temporary directory. Clean up old
files. The upstream helper writes to `/tmp/dump` and notes that `/tmp` is shared
across satellite containers; verify that path in the target environment before
relying on it. If capture retrieval is too fragile for class, an ASCII
`tcpdump -nn -A -c N` summary is a lower-effort fallback.

### Unit 5 - Integrity and trust: spoofing a source address (30 min, live)

`hping3` can set a spoofed source address with `-a`, assert TCP flags, and send
at a chosen rate. The GUI currently hides those options.

1. From an attacker node, send TCP SYN packets with a forged source address to
   a target. Use `flags=["S"]` and `spoof_src=<victim address>`.
2. Capture at the target. If the lab adapter can also capture on the victim
   ground station, show the replies arriving there; the built-in helper only
   starts `tcpdump` on satellites, so a ground-station capture needs a custom
   command. Show the forged source in the capture and the absence of a completed
   handshake.
3. Discuss why an IP source address is not an identity, why ingress/egress
   filtering (BCP 38) matters, and what changes when commands must be
   authenticated and replay-protected.
4. Connect to the ground segment: a forged telecommand is a much bigger problem
   than a forged ping.

GUI work: add `spoof_src`, `sport`, and `ttl` to the hping3 request schema and
adapter, and expose `flags` plus the new fields only in the security lab (not as
general traffic options) to keep the traffic page simple. Verify return-path
behaviour in the container network before class.

### Policy and QoS lab (live, policy workstream)

This is the defense counterpart to the DDoS unit. Students apply a policy to a
node, inspect the exact plan, and use counters to see what the rule matched.

1. Preview a default-deny policy for a ground station or satellite. Read the
   generated `iptables`/`ip6tables` chain and the warnings before applying it.
2. Apply the policy, then inspect the rule counters. Confirm that loopback and
   established traffic still work, then clear the policy and confirm the saved
   ruleset was restored.
3. Run the DDoS lab. While the attack is active, use **Apply mitigation to
   target**. The page builds a source-specific rate/connection limit for the
   attacker IP and leaves the legitimate iperf3 flow in the default-accept
   policy.
4. Compare throughput before, during, and after mitigation. If the original
   TCP flow collapses before the policy lands, start a fresh baseline while the
   policy is applied; the mitigation counters should show the flood being
   dropped. Clear the policy and confirm the attack effect returns.
5. Optional: compare `DROP` with `REJECT --reject-with tcp-reset` and measure
   CPU/reply differences (see [`ideas.md`](ideas.md) for the detailed lab).

The policy schema covers:

- default inbound accept/drop, established/related, loopback, ICMP;
- management, TT&C, and telemetry source/port allowlists;
- BCP38 ingress rpfilter and explicit egress source CIDRs;
- per-source hashlimit rate limits, including SYN-only limits;
- per-source connection limits;
- custom accept/drop/reject rules;
- ingress policing with a `tc` u32 police filter;
- DSCP marking in the mangle table.

API:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/security/policies/preview` | Build the command plan without changing the node |
| POST | `/api/security/policies` | Apply/replace a policy and return counters |
| GET | `/api/security/policies/{node}` | Read chain status and counters |
| POST | `/api/security/policies/{node}/clear` | Restore the saved ruleset |
| GET | `/api/security/policies` | List policies applied in this process |

Limitations:

- The existing root qdisc is owned by SatGoNetEm's netem/TBF setup. The policy
  layer applies ingress policing and DSCP marking; full egress per-flow class
  scheduling needs a coordinated SatGoNetEm qdisc change.
- `rpfilter` is IPv4-only in the current image; IPv6 BCP38 egress uses explicit
  source CIDRs.
- The controller is GUI-local. The GUI has no authentication, so policy apply
  and clear are trusted-local actions.

### Unit 6 - Ground segment, firmware, crypto, and GNSS (45 min, tabletop)

These are the parts SatGoNetEm does not model, and the section should say so
plainly:

- **Ground segment compromise.** A GSaaS management host, a shared ground
  station, or a vendor access path can become the entry point to the mission.
  Walk through the KA-SAT/AcidRain and Dozor cases.
- **Firmware and update integrity.** The emulator does not run satellite
  firmware, so this is a tabletop: signed updates, secure boot, least privilege,
  staged rollout, and rollback. Use the "Space Odyssey" findings as the reading.
- **Cryptography.** The emulated links can carry a custom key-exchange or
  broadcast exercise, but SatGoNetEm has no built-in crypto lesson. A common
  factor RSA exercise is possible as an application-level capstone if the image
  has Python/OpenSSL; otherwise keep it as a tabletop.
- **GNSS jamming and spoofing.** No RF layer is modelled. Discuss the threat and
  the defences; HIL can bridge real ground equipment, but SDR integration would
  be custom work.

Exercise: given a network diagram, draw the attack path from the internet to a
satellite, list the controls that would break the path, and write a five-step
incident-response outline. This is also where students learn to distinguish
"demonstrated in the range" from "described in the literature".

### Unit 7 - Capstone: red team vs blue team (90 min, live)

Split the class. Give each team a written rules-of-engagement card.

- Red team: recon, choose a target, run one or more allowed actions (flood,
  link failure, spoof), and achieve a measurable objective, for example
  "reduce Gnd0-to-Gnd1 throughput by at least 50% for 60 seconds."
- Blue team: monitor the dashboard and capture, detect the anomaly, identify
  the cause, contain it (stop the job, reroute, restore the link, isolate the
  node), and write a short incident report with evidence.
- Instructor: reset the range between rounds and score detection time, time to
  contain, quality of evidence, and whether the mitigation actually worked.

This unit is where the section becomes a course rather than a set of demos. It
needs a reset path and an instructor view more than it needs new attack tools.

## GUI design

Add one page, `/security`, with a navigation link next to "Traffic". Do not
duplicate the traffic page; the security page orchestrates existing flows and
adds topology controls.

```text
+-----------------------------------------------------------------------+
| Space Cybersecurity Lab                    [Training range - isolated] |
| Range: project loaded | containers up | addressing | routing          |
+------------------+----------------------------------------------------+
| Units            |  Unit 2 - Saturating an ISL                        |
| 0 Threat model   |  Briefing  |  Run  |  Observe  |  Debrief          |
| 1 Recon          |                                                    |
| 2 Availability   |  Target: [Sat12 v]  Link: [Gnd0-Sat12 v]           |
| 3 Resilience     |  Baseline: [Run 20 s]  Attack: [Launch] [Stop]     |
| 4 Confidentiality|                                                    |
| 5 Trust          |  Throughput  ######################### 42 Mbps     |
| 6 Tabletop       |  Loss        ####                      18%          |
| 7 Capstone       |  Event log: 12:00:03 baseline started ...           |
|                  |  [Export observations]  [Reset lab]                |
+------------------+----------------------------------------------------+
```

Key elements:

- **Readiness strip.** Project loaded, GoNetEm running, addressing applied,
  routing applied. Labs are disabled until the range is ready. This prevents the
  most common class failure: starting an attack before the containers exist.
- **Unit rail.** Each unit shows a one-line objective and a completion mark.
- **Briefing tab.** Two or three short paragraphs, the real-world case, and the
  exact commands/actions the student is about to trigger. No hidden magic.
- **Run tab.** Target/link/attacker selectors populated from the topology.
  Baseline and attack buttons, duration, intensity, and a large Stop. Show the
  estimated effect ("this will send N packets over T seconds").
- **Observe tab.** One live chart with throughput, loss, and RTT; an event log;
  a route diff after link failure; a capture list after eavesdropping. Reuse the
  existing Chart.js and queue result shapes where possible.
- **Debrief tab.** Three to five questions with free-text answers, plus an
  "export observations" button (Markdown or JSON) for the student's report.
- **Policy tab.** Node policy editor with preset selection, preview/diff,
  apply, clear, rule counters, and QoS warnings. The DDoS panel can apply a
  source-specific mitigation while the attack is running.
- **Instructor mode.** A query parameter or toggle that reveals answer notes,
  suggested timings, reset controls, and the scoring rubric. Do not ship the
  answer key in the student bundle if the course uses it for assessment.

### Safety affordances

- A persistent banner: "Training range. Attacks are confined to the emulated
  constellation. Do not point these tools at real networks."
- Per-lab duration and packet caps; the Stop button cancels the underlying flow.
- No free-form command box. Every action is a typed lab operation.
- Reset restores the pre-lab topology and clears jobs, captures, and charts.
- The README already says the GUI has no authentication and binds loopback by
  default. Keep that. If students need remote access, put the GUI behind an
  authenticating reverse proxy.

## Implementation shape

Follow the existing route -> service -> port -> adapter direction.

```text
routes/security.py          thin HTTP translation for the five labs
routes/policies.py          policy preview/apply/status/clear
services/security_service.py orchestration of labs and runs
services/policy_service.py  policy orchestration and replace/rollback
services/ports.py           SecurityGateway and PolicyGateway protocols
adapters/satgonetem_security.py  link inventory, failure, capture, reset
adapters/satgonetem_policy.py    iptables/ip6tables and tc policy commands
schemas.py                  lab and policy request/response models
static/security.js          module UI and polling
static/security.css         page styles
templates/security.html     page shell
data/security/*.json        lab definitions and range presets
```

Suggested API surface:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/security/range` | Readiness, nodes, links with capacity/delay, routing methods |
| GET | `/api/security/labs` | Lab catalogue and parameters |
| POST | `/api/security/labs/{lab}/runs` | Start a lab run; returns a run id |
| GET | `/api/security/runs/{run_id}` | Status, metrics, events |
| POST | `/api/security/runs/{run_id}/stop` | Stop the run |
| POST | `/api/security/runs/{run_id}/reset` | Restore the range |
| GET | `/api/security/captures` | List captured files |
| GET | `/api/security/captures/{name}` | Download a capture |

The lab run should be asynchronous, like the existing project and traffic
operations. Do not block the event loop on container calls; use
`asyncio.to_thread` in the service, as `RoutingService` already does.

### Backend capabilities to add

1. **Link inventory.** Extend the link serializer with `capacity_kbps`,
   `delay_ms`, state, and a stable key. The current `/api/links` response has
   endpoints, type, direction, and distance only.
2. **Link failure and impairment.** Wrap `simulate_link_failure()` and, if it
   proves reliable, reversible netem loss/jitter updates. Map dependency errors
   to the existing error envelope.
3. **Capture lifecycle.** Start `tcpdump` on a selected node/interface with a
   packet cap, stop it, list files, and serve downloads. Keep files in a
   dedicated temporary directory with a size cap and TTL cleanup.
4. **Range reset.** Snapshot the project before a destructive lab and restore
   it afterward. Because `simulate_link_failure()` removes links, a reset may
   need a stop/rebuild/start sequence, not just a reload. Measure this before
   promising one-click reset.
5. **Extended hping3.** Add `spoof_src`, `sport`, and `ttl` to the request
   model and adapter, and add the lab UI for `flags`. Keep validation tight:
   flags are a fixed set; addresses must be nodes or explicit IPv4 values;
   counts and durations are bounded.

### Range preset

Ship a dedicated security range rather than asking students to build one:

- 3 ground stations (Berlin, Madrid, Rome), 24 satellites, one Walker shell.
- Low link capacity (5000 Kbps) and realistic delays.
- Static routing by default; OSPF/IS-IS selectable for unit 3.
- A documented "attacker" node and "victim" service so every student starts
  from the same topology.
- The preset lives at `satgonetem_gui/data/security/range.json` and is exposed
  through `GET /api/security/preset`; the page's **Load SatSec range** button
  submits it to the existing project builder.

The existing project builder can create it; no new constellation code is needed.

## Implementation phases

| Phase | Contents | Status |
|---|---|---|
| A | `/security` page shell, readiness, link inventory, reconnaissance | Implemented (#15) |
| B | DDoS baseline/attack runner over existing traffic jobs | Implemented (#16) |
| C | Link failure, route diff, reset, routing comparison | Implemented (#17) |
| D | Capture lifecycle and pcap download | Implemented (#18) |
| E | Spoofing fields, trust lab, capture evidence | Implemented (#19) |
| F | Docs, browser coverage, real-container verification | Implemented (#20) |
| G | Firewall/QoS policy API, policy panel, DDoS mitigation | Implemented (#21 workstream 1) |

The labs share the bundled range through **Load SatSec range**. The
default suite covers their orchestration with fakes. The destructive reset and
capture paths were verified against a real GoNetEm server with the opt-in test
below.

## Real-container verification

With a running GoNetEm server and Docker:

```bash
SATGONETEM_RUN_CONTAINER_TESTS=1 .venv/bin/pytest \
  tests/test_security_container_contract.py -s
```

The test builds the 24-satellite SatSec range, starts the containers, applies
static routing, applies a firewall/DSCP policy and clears it, fails one
inter-satellite link, captures a pcap on `Sat0`, stops the capture, resets the
range, and checks that the failed-link list is empty and the original link
count is restored. A separate manual run after the
reset completed a 3-packet ping with 3/3 replies, confirming that the rebuilt
addressing and routing were usable.

## Class formats

| Time | Format | Units |
|---|---|---|
| 45-60 min | Lecture/demo | 0, 2 (demo only), 6 (discussion) |
| 90 min | Guided lab | 0, 1, 2 (compressed timings), debrief |
| 3 h | Hands-on workshop | 0-5 (compressed timings), debrief |
| Multi-week | Course/capstone | 0-7, with reading and incident report |

## Limits and risks

- **No RF layer.** Jamming and GNSS spoofing cannot be demonstrated faithfully.
  Packet loss is an analogue, not a radio model. Say this before the lab.
- **No firmware or onboard OS.** Ground-segment-to-firmware attacks are a
  tabletop unless a custom vulnerable service is added.
- **No built-in cryptography.** Crypto exercises need application-level scripts
  in the containers, and those depend on the image's tooling.
- **Resource use.** `hping3 --flood` can saturate the host's CPU or network.
  Cap duration and packet count, prefer low-capacity links, and test the
  classroom hardware before the session.
- **Reset semantics.** Link failure is destructive to the topology object.
  The opt-in container test verifies the stop/rebuild/start reset, but re-run it
  on the classroom host because container startup time and image state vary.
- **No authentication.** The GUI is a local teaching tool, not a multi-user
  range. Do not expose it to students over an untrusted network without an
  authenticating proxy.
- **Image tooling.** Verify `hping3`, `tcpdump`, and any crypto/HTTP tools in
  the actual satellite and ground-station images before writing exercises that
  depend on them.

## References

- SatGoNetEm paper (hping3 for attack simulation, tcpdump for packet analysis,
  link impairments, routing modes):
  <https://opendl.ifip-tc6.org/db/conf/networking/networking2026/1571253461.pdf>
- SatGoNetEm documentation (traffic, routing, topology API):
  <https://github.com/satcomprojects/satgonetem/tree/main/docs>
- OpenSatRange training scenarios (ground segment, crypto, DDoS, firmware):
  <https://ceur-ws.org/Vol-3978/regular-s3-04.pdf>
- OpenSatRange platform paper:
  <https://ceur-ws.org/Vol-3731/paper18.pdf>
- ESA "Simulating and Observing Satellite Threats" slides:
  <https://indico.esa.int/event/571/attachments/7210/13604/Simulating%20and%20Observing%20Satellite%20Threats.pdf>
- ICARUS: Attacking Low Earth Orbit Satellite Networks:
  <https://www.usenix.org/conference/atc21/presentation/giuliari>
