# SatSec lab ideas

Status: proposed, not implemented. These extend the five SatSec labs in
[`docs/security-section.md`](docs/security-section.md).

Two concrete additions:

1. **Drop vs REJECT** - show that generating reject responses costs CPU while a
   silent drop does not.
2. **WireGuard ground-station tunnel** - build an encrypted overlay across the
   emulated constellation and measure what it protects and what it exposes.

## Feasibility check

Checked on the development host with the current images and a real
GoNetEm-launched constellation:

- The host has the `wireguard` kernel module.
- GoNetEm-launched containers are privileged (`Privileged=true`,
  `CapAdd=["ALL"]`).
- `iptables` can add `REJECT --reject-with tcp-reset` and `DROP` rules inside a
  node container.
- `ip link add wg0 type wireguard` succeeds inside a node container.
- The satellite image does **not** currently ship `wg`/`wg-quick`; adding
  `wireguard-tools` to the image is required to configure keys and peers.
- The ground-station image has `iptables`, `tc`, `tcpdump`, Python, Bird, and
  `vtysh`; it does not include OpenSSL or `curl`.
- Deleting an iptables rule requires the exact rule text (iptables expands
  `--dport` to `-m tcp --dport`), so the lab should use `iptables-save` /
  `iptables-restore` rather than ad-hoc `-D` commands.

## Idea 1: Drop vs REJECT under a TCP SYN flood

### Question

If a host is flooded with TCP SYNs, does answering them with RSTs cost more CPU
than silently dropping them? Which rule placement is cheapest?

### Why it is interesting

`REJECT --reject-with tcp-reset` makes the kernel generate a response for every
matched packet. `DROP` discards the packet without a response. The difference
is small at low rates and visible at high packet rates. It is a practical lesson
in firewall placement and in why "just reject everything" can make a DoS worse.

### Topology

- One attacker ground station.
- One victim ground station or satellite with a target port.
- A link capacity high enough to generate meaningful packet rates; for the
  bundled 5 Mbps range, use a dedicated high-capacity variant or multiple
  attackers, otherwise the link is the bottleneck and CPU differences disappear.
- Target port: start with a closed port (for example 59999) so the comparison is
  about netfilter behavior, not an application's accept queue. Repeat with a
  listening service as an advanced variant.

### Procedure

1. Establish a control run: attack with no custom rule. Record CPU, packet
   counters, and hping3 replies.
2. Add:
   ```bash
   iptables -I INPUT -p tcp --dport 59999 -j REJECT --reject-with tcp-reset
   ```
   Repeat the same flood for the same duration.
3. Replace it with:
   ```bash
   iptables -I INPUT -p tcp --dport 59999 -j DROP
   ```
   Repeat.
4. Optional: compare `DROP` in `INPUT` with an early `DROP` in `raw PREROUTING`.
5. Restore the saved ruleset and repeat the control run to show the measurement
   is stable.

### Measurements

- Per-second CPU of the target container (`docker stats` is convenient but may
  not attribute all softirq work; always sample host CPU too).
- Host CPU (`mpstat -P ALL 1`, `pidstat`, `top`).
- `nstat -az` or `/proc/net/snmp`: `TcpOutRsts`, `IpInReceives`,
  `IpInDelivers`, `IpInDiscards`.
- hping3 replies/loss in the traffic job results.
- Optional: `ss -s`, `/proc/softirqs`, and `perf top` on the host.

### Expected result

- `REJECT` produces RSTs and generally costs more CPU than `DROP`.
- `DROP` removes the response traffic and reduces CPU, but does not necessarily
  reach zero; packet reception, netfilter traversal, and softirq handling remain.
- Early `DROP` (raw PREROUTING) should be cheaper than late `DROP` (INPUT) when
  conntrack or later hooks are involved.
- The chart should show the three phases and the reply count, not just CPU.

### Implementation

- Add a small **policy API** to the SatGoNetEm side rather than raw shell:
  `apply_firewall(node, rules)`, `clear_firewall(node)`, `firewall_status(node)`.
- Generate rules with `iptables-restore` so apply/rollback are idempotent.
- Capture rule counters and export them as metrics.
- Add a scenario definition with phases (`control`, `reject`, `drop`) and
  per-phase duration/rate.
- GUI: phase timeline, CPU chart, reply/loss chart, rule diff, reset button.
- Test with fake adapters; add an opt-in real-container test that applies the
  rules, runs a short flood, and asserts the rule set is restored.

### Caveats

- CPU attribution is the hard part. Container cgroup CPU may miss softirq work;
  report both container and host measurements.
- At 5 Mbps, the link saturates before the CPU does; this lab needs a
  high-capacity profile or multiple attackers.
- Default Linux behavior for a closed port is already RST. Explain that
  `REJECT --reject-with tcp-reset` makes the policy explicit; the interesting
  comparison is REJECT vs DROP, not "no rule vs reject".
- Do not claim CPU reaches exactly zero after DROP.

## Idea 2: WireGuard tunnel between ground stations

### Question

What does an encrypted overlay protect when the underlay is an emulated
satellite constellation, and what does it still expose?

### Topology

```text
GndA  ──  satellite path  ──  GndB
  wg0 10.99.0.1/32              wg0 10.99.0.2/32
        \______________________/
          WireGuard over UDP/51820
```

- Use two ground stations with a working route between their underlay addresses.
- Create `wg0` on each station.
- Tunnel addresses: `10.99.0.1/32` and `10.99.0.2/32`.
- Peer `AllowedIPs`: the other tunnel address only.
- `PersistentKeepalive = 5` for a NAT-like or intermittent underlay.
- Choose a stable underlay interface address for `Endpoint`; verify it with a
  plain ping before starting.

### Procedure

1. Baseline: ping and iperf3 between the ground stations over the emulated path.
2. Generate key pairs, configure `wg0`, and bring the tunnel up.
3. Ping the tunnel addresses; run iperf3 over the tunnel.
4. Capture on an on-path satellite:
   - outer UDP 51820 and endpoint addresses;
   - encrypted payload;
   - packet sizes and timing.
5. Compare with a plaintext flow: same metadata, different payload visibility.
6. Fail a link or switch routing; observe handshake/retry and recovery.
7. Rotate one peer key; show the old key stops working and the new key restores
   the tunnel.
8. Add a firewall rule blocking UDP 51820; show the tunnel goes down while other
   traffic still works.

### Measurements

- Tunnel handshake age and transfer counters (`wg show`).
- RTT and throughput: underlay vs tunnel.
- MTU effect: WireGuard's default 1420-byte MTU; test large packets and MSS
  clamping.
- Packet loss/recovery after link failure and key rotation.
- Pcap size and visible metadata.

### Security lessons

- WireGuard provides confidentiality, integrity, and peer authentication.
- Endpoints, ports, packet sizes, and timing remain visible; it is not
  traffic-analysis protection.
- Key distribution and rotation are the operational hard part.
- A tunnel does not protect the underlay from DoS, jamming, or routing attacks.
- WireGuard is an overlay, not a substitute for link-layer or RF security.

### Implementation

- Add `wireguard-tools` (`wg`, `wg-quick`) to the satellite/ground-station
  images, or ship a small `wg` helper. Kernel support is already present.
- Add a SatGoNetEm-side `WireGuardTunnel` service:
  - generate/accept keys;
  - create the interface and addresses;
  - set peer endpoint, allowed IPs, and keepalive;
  - read status and counters;
  - apply/rollback/rotate.
- Do not put private keys in the GUI or repository. Generate them per lab run
  and keep them in a temporary runtime directory.
- Expose a scenario definition with phases: baseline, tunnel up, capture,
  link failure, key rotation, firewall block.
- GUI: tunnel status panel (handshake age, bytes, endpoint, peer key
  fingerprint), capture button, key rotation, reset.
- Add an opt-in real-container test: create the tunnel, ping through it, read
  counters, rotate keys, and tear it down.

### Caveats

- Underlay endpoint addresses can change as the constellation topology or
  handover changes. Start with a static topology; then add endpoint roaming.
- If a container image lacks `wg`, kernel WireGuard interfaces can be created
  but cannot be configured. Add the tool rather than shelling out to a
  half-working netlink path.
- WireGuard MTU and fragmentation can distort throughput results; document the
  MTU and use a consistent payload size.
- The tunnel adds encapsulation overhead and another failure domain; measure
  both underlay and tunnel before drawing conclusions.

## Shared work

Both ideas need the same core pieces:

- A typed **node security agent** in SatGoNetEm: firewall, traffic control,
  WireGuard, capture, and status. No free-form shell.
- **Idempotent apply/rollback** with saved state and explicit cleanup.
- **Events and metrics** for rule changes, tunnel state, CPU, and counters.
- **Scenario definitions** with phases, durations, and reset semantics.
- **GUI panels** that show the timeline and evidence, not just buttons.
- **Opt-in real-container tests**; fake-backed unit tests for the default suite.

## Suggested order

1. Firewall policy API and the drop-vs-reject lab.
2. WireGuard tooling in the images and the tunnel lab.
3. Detection alerts on top of both: RST storms, SYN rates, tunnel handshake
   failures, and firewall counter spikes.
4. Link-budget interference and TLE integrity as the next satellite-specific
   labs.

## Open questions

- Should the drop-vs-reject lab use a closed port or a listening service?
- Is host CPU or container CPU the primary graded metric?
- Should WireGuard keys be generated per run or loaded from a scenario fixture?
- Do we want a separate `sgnt-monitor`/`sgnt-tools` image, or add packages to the
  existing node images?
