import { expect, test } from "@playwright/test";

const nodes = [
  { name: "Sat0", type: "satellite", id: 0, shell: "LEO", position: { latitude: 0, longitude: 0, altitude: 550 } },
  { name: "Sat1", type: "satellite", id: 1, shell: "LEO", position: { latitude: 1, longitude: 1, altitude: 550 } },
  { name: "Sat2", type: "satellite", id: 2, shell: "MEO", position: { latitude: 2, longitude: 2, altitude: 2000 } },
  { name: "Gnd0", type: "ground_station", id: 100, city: "Berlin", position: { latitude: 52, longitude: 13, altitude: 0 } },
  { name: "Gnd1", type: "ground_station", id: 101, city: null, position: { latitude: 0, longitude: 10, altitude: 0 } },
];

const links = [
  { src: "Sat0", dst: "Sat1", type: "InterSatelliteLink", delay_ms: 1.2, capacity_kbps: 100000, loss_percent: 0, jitter_ms: 0, is_active: true },
  { src: "Sat0", dst: "Gnd0", type: "GroundStationLink", delay_ms: 4.2, capacity_kbps: 50000, loss_percent: 0.5, jitter_ms: 3, is_active: true },
  { src: "Sat2", dst: "Gnd1", type: "GroundStationLink", delay_ms: 7.5, capacity_kbps: 50000, loss_percent: 0, jitter_ms: 0, is_active: true },
];

const detail = {
  ok: true,
  node: {
    name: "Sat0",
    type: "satellite",
    position: { latitude: 0, longitude: 0, altitude: 550 },
    interfaces: [{ name: "eth0", ipv4: "10.0.0.1", peer_name: "Sat1", type: "isl" }],
    routing_table: ["10.0.0.0/8 via 10.0.0.1 dev eth0"],
  },
};

async function mockTopology(page) {
  await page.route("**/api/nodes*", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: links });
  });
  await page.route("**/api/nodes/Sat0", async (route) => {
    await route.fulfill({ json: detail });
  });
  await page.route("**/api/routing/path*", async (route) => {
    await route.fulfill({
      json: {
        src: "Sat0",
        dst: "Gnd0",
        found: true,
        hops: [{ source: "Sat0", target: "Gnd0" }],
        node_count: 1,
        total_delay_ms: 4.2,
      },
    });
  });
}

test("topology graph filters, inspects, partitions, and traces", async ({
  page,
}) => {
  await mockTopology(page);
  await page.goto("/topology");

  await expect(page.locator(".topo-node")).toHaveCount(5);
  await expect(page.locator(".topo-satellite")).toHaveCount(3);
  await expect(page.locator(".topo-ground")).toHaveCount(2);
  await expect(page.locator("#topo-count")).toHaveText("5 nodes \u00b7 3 links");
  await expect(page.locator("#topo-partition-count")).toHaveText("2 partitions");

  await page.locator("#topo-shell").selectOption("LEO");
  await expect(page.locator(".topo-node")).toHaveCount(4);

  await page.locator("#topo-shell").selectOption("all");
  await page.locator("#topo-type").selectOption("ground_station");
  await expect(page.locator(".topo-node")).toHaveCount(2);
  await expect(page.locator(".topo-edge")).toHaveCount(0);
  await page.locator("#topo-type").selectOption("all");

  await page.locator('[data-name="Sat0"]').click();
  await expect(page.locator("#topo-inspector")).toBeVisible();
  await expect(page.locator("#topo-inspector-title")).toHaveText("Sat0");
  await expect(page.locator("#topo-inspector-interfaces")).toContainText(
    "10.0.0.1",
  );
  await expect(page.locator("#topo-inspector-routing")).toContainText(
    "10.0.0.0/8",
  );
  await page.locator("#topo-inspector-close").click();
  await expect(page.locator("#topo-inspector")).toBeHidden();

  await page.locator("#topo-path-src").selectOption("Sat0");
  await page.locator("#topo-path-dst").selectOption("Gnd0");
  await page.locator("#topo-path-trace").click();
  await expect(page.locator(".topo-edge.path")).toHaveCount(1);
  await expect(page.locator("#topo-path-summary")).toContainText(
    "Sat0 \u2192 Gnd0",
  );

  await page.locator("#topo-partitions").check();
  await expect(page.locator(".topo-node.topo-component-0").first()).toBeVisible();
});

test("topology graph shows the no-project state", async ({ page }) => {
  await page.route("**/api/nodes*", async (route) => {
    await route.fulfill({
      status: 404,
      json: { ok: false, error: "No project is currently loaded." },
    });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({
      status: 404,
      json: { ok: false, error: "No project is currently loaded." },
    });
  });

  await page.goto("/topology");

  await expect(page.locator("#topo-msg")).toContainText("Load a project");
  await expect(page.locator("#topo-empty")).toBeVisible();
});
