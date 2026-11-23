import { expect, test } from "@playwright/test";

const nodes = [
  { name: "Sat0", type: "satellite", shell: "LEO", city: null, position: { latitude: 0, longitude: 0, altitude: 550 } },
  { name: "Sat1", type: "satellite", shell: "LEO", city: null, position: { latitude: 1, longitude: 1, altitude: 550 } },
  { name: "Sat2", type: "satellite", shell: "MEO", city: null, position: { latitude: 2, longitude: 2, altitude: 2000 } },
  { name: "Gnd0", type: "ground_station", city: "Berlin", position: { latitude: 52, longitude: 13, altitude: 0 } },
  { name: "Gnd1", type: "ground_station", city: null, position: { latitude: 0, longitude: 10, altitude: 0 } },
];

const links = [
  { src: "Sat0", dst: "Sat1", type: "InterSatelliteLink", delay_ms: 1.2, capacity_kbps: 100000, loss_percent: 0, jitter_ms: 0, is_active: true },
  { src: "Sat0", dst: "Gnd0", type: "GroundStationLink", delay_ms: 4.2, capacity_kbps: 50000, loss_percent: 0.5, jitter_ms: 3, is_active: true },
  { src: "Sat2", dst: "Gnd1", type: "GroundStationLink", delay_ms: 7.5, capacity_kbps: 50000, loss_percent: 0, jitter_ms: 0, is_active: true },
  { src: "Gnd0", dst: "Sat1", type: "GroundStationLink", delay_ms: 5.0, capacity_kbps: 50000, loss_percent: 0, jitter_ms: 0, is_active: true },
];

const snapshots = {
  ok: true,
  generation: 1,
  snapshots: [
    { step: 0, time: "T0", recorded_at: "2026-01-01T00:00:00Z", node_count: 5, link_count: 4 },
    { step: 1, time: "T1", recorded_at: "2026-01-01T00:00:05Z", node_count: 5, link_count: 4 },
  ],
};

const comparison = {
  ok: true,
  from: snapshots.snapshots[0],
  to: snapshots.snapshots[1],
  added_links: [
    { src: "Gnd0", dst: "Sat1", type: "GroundStationLink", delay_ms: 5, capacity_kbps: 50000, loss_percent: 0, jitter_ms: 0, is_active: true },
  ],
  removed_links: [
    { src: "Sat2", dst: "Gnd1", type: "GroundStationLink", delay_ms: 7.5, capacity_kbps: 50000, loss_percent: 0, jitter_ms: 0, is_active: true },
  ],
  changed_links: [],
  added_nodes: [],
  removed_nodes: [],
};

test("topology page records and compares snapshots", async ({ page }) => {
  await page.route("**/api/nodes*", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: links });
  });
  await page.route("**/api/topology/snapshots", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          ok: true,
          recorded: true,
          step: 0,
          snapshot_count: 2,
          node_count: 5,
          link_count: 4,
        },
      });
      return;
    }
    await route.fulfill({ json: snapshots });
  });
  await page.route("**/api/topology/compare*", async (route) => {
    await route.fulfill({ json: comparison });
  });

  await page.goto("/topology");
  await expect(page.locator("#topo-snapshot-count")).toContainText("recorded");
  await expect(page.locator("#topo-compare")).toBeEnabled();
  await expect(page.locator("#topo-compare-from option")).toHaveCount(2);

  await page.locator("#topo-compare-from").selectOption("0");
  await page.locator("#topo-compare-to").selectOption("1");
  await page.locator("#topo-compare").click();

  await expect(page.locator("#topo-compare-msg")).toContainText(
    "1 added / 1 removed",
  );
  await expect(page.locator("#topo-compare-table")).toContainText("Added");
  await expect(page.locator("#topo-compare-table")).toContainText("Removed");
  await expect(page.locator(".topo-edge.added")).toHaveCount(1);
  await expect(page.locator(".topo-edge.removed").first()).toBeAttached();
});
