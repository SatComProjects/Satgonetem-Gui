import { expect, test } from "@playwright/test";

const nodes = [
  { name: "Gnd100", type: "ground_station", id: 100, city: "Berlin", position: {} },
  { name: "Sat0", type: "satellite", id: 0, position: {} },
  { name: "Sat42", type: "satellite", id: 42, position: {} },
];

const pathPayload = {
  ok: true,
  src: "Gnd100",
  dst: "Sat42",
  found: true,
  hops: [
    {
      source: "Gnd100",
      target: "Sat28",
      type: "GroundStationLink",
      direction: null,
      distance_km: 1000,
      delay_ms: 3.34,
      cumulative_distance_km: 1000,
      cumulative_delay_ms: 3.34,
    },
    {
      source: "Sat28",
      target: "Sat42",
      type: "InterSatelliteLink",
      direction: "ORBITAL",
      distance_km: 4000,
      delay_ms: 13.34,
      cumulative_distance_km: 5000,
      cumulative_delay_ms: 16.68,
    },
  ],
  node_count: 3,
  total_distance_km: 5000,
  total_delay_ms: 16.68,
  routing_method: "static",
  routing_initiated: false,
  preference: "latency_no_preference",
  path_source: "routing_graph",
  note: "Computed over the current routing graph; this is a diagnostic path, not the live forwarding table.",
};

async function stubNodes(page) {
  await page.route("**/api/nodes?*", async (route) => {
    await route.fulfill({ json: nodes });
  });
}

test("nodes page traces and renders a forwarding path", async ({ page }) => {
  await stubNodes(page);
  await page.route("**/api/routing/path?*", async (route) => {
    await route.fulfill({ json: pathPayload });
  });

  await page.goto("/nodes");
  await expect(page.locator("#path-src")).toBeEnabled();
  await page.selectOption("#path-src", "Gnd100");
  await page.selectOption("#path-dst", "Sat42");
  await page.locator("#path-trace").click();

  await expect(page.locator("#path-summary")).toContainText("3 nodes");
  await expect(page.locator("#path-summary")).toContainText("static");
  await expect(page.locator("#path-msg")).toContainText("not the live forwarding table");
  await expect(page.locator("#path-table-body tr")).toHaveCount(2);
  await expect(page.locator("#path-table-body")).toContainText("Gnd100 → Sat28");
  await expect(page.locator("#path-table-body")).toContainText("ISL");
  await expect(page.locator("#path-actions")).toBeVisible();
  await expect(page.locator("#path-copy")).toBeVisible();
  await expect(page.locator("#path-export")).toBeVisible();
});

test("nodes page reports a missing path without opening the table", async ({ page }) => {
  await stubNodes(page);
  await page.route("**/api/routing/path?*", async (route) => {
    await route.fulfill({
      json: {
        ...pathPayload,
        found: false,
        hops: [],
        node_count: 0,
        total_distance_km: 0,
        total_delay_ms: 0,
        note: "Computed over the current routing graph; no path connects these nodes.",
      },
    });
  });

  await page.goto("/nodes");
  await expect(page.locator("#path-src")).toBeEnabled();
  await page.selectOption("#path-src", "Gnd100");
  await page.selectOption("#path-dst", "Sat42");
  await page.locator("#path-trace").click();

  await expect(page.locator("#path-summary")).toContainText("No path found");
  await expect(page.locator("#path-table-wrap")).toBeHidden();
  await expect(page.locator("#path-actions")).toBeHidden();
});
