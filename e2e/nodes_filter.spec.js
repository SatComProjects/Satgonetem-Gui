import { expect, test } from "@playwright/test";

const nodes = [
  {
    name: "Sat2",
    type: "satellite",
    id: 2,
    city: null,
    position: { latitude: 1, longitude: 2, altitude: 550 },
  },
  {
    name: "Sat10",
    type: "satellite",
    id: 10,
    city: null,
    position: { latitude: 3, longitude: 4, altitude: 550 },
  },
  {
    name: "Gnd0",
    type: "ground_station",
    id: 100,
    city: "Berlin",
    position: { latitude: 52.5, longitude: 13.4, altitude: 0 },
  },
  {
    name: "Gnd1",
    type: "ground_station",
    id: 101,
    city: "Oslo",
    position: { latitude: 59.9, longitude: 10.7, altitude: 0 },
  },
  {
    name: "Gnd2",
    type: "ground_station",
    id: 102,
    city: null,
    position: { latitude: 0, longitude: 0, altitude: 0 },
  },
];

const health = {
  ok: true,
  nodes: 5,
  links: 0,
  healthy: true,
  checks: [],
};

async function mockNodes(page) {
  await page.route("**/api/nodes*", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/topology/health", async (route) => {
    await route.fulfill({ json: health });
  });
}

test("node explorer filters, sorts, and counts nodes", async ({ page }) => {
  await mockNodes(page);
  await page.goto("/nodes");
  await expect(page.locator(".node-row")).toHaveCount(5);
  await expect(page.locator("#node-count")).toHaveText("5 nodes");

  await page.locator("#node-search").fill("berlin");
  await expect(page.locator(".node-row")).toHaveCount(1);
  await expect(page.locator(".node-row").first()).toContainText("Gnd0");
  await expect(page.locator("#node-count")).toHaveText("Showing 1 of 5 nodes");

  await page.locator("#node-search").fill("");
  await page.locator("#node-type-filter").selectOption("satellite");
  await expect(page.locator(".node-row")).toHaveCount(2);
  await expect(page.locator("#card-ground-stations")).toBeHidden();
  await expect(page.locator("#node-count")).toHaveText("Showing 2 of 5 nodes");

  await page.locator("#node-type-filter").selectOption("all");
  await page.locator("#node-sort").selectOption("city");
  await expect(
    page.locator("#ground-stations-list .node-label").first(),
  ).toHaveText("Gnd0 (Berlin)");
  await expect(
    page.locator("#satellites-list .node-label").first(),
  ).toHaveText("Sat2");
});

test("node favorites persist and filter the list", async ({ page }) => {
  await mockNodes(page);
  await page.goto("/nodes");
  await expect(page.locator(".node-row")).toHaveCount(5);

  await page
    .locator('#row-Gnd1 [data-action="favorite"]')
    .click();
  await expect(
    page.locator('#row-Gnd1 [data-action="favorite"]'),
  ).toHaveAttribute("aria-pressed", "true");

  await page.locator("#node-favorites-only").check();
  await expect(page.locator(".node-row")).toHaveCount(1);
  await expect(page.locator(".node-row").first()).toContainText("Gnd1");
  await expect(page.locator("#node-count")).toHaveText("Showing 1 of 5 nodes");

  await page.reload();
  await expect(page.locator(".node-row")).toHaveCount(5);
  await expect(
    page.locator('#row-Gnd1 [data-action="favorite"]'),
  ).toHaveAttribute("aria-pressed", "true");
  await page.locator("#node-favorites-only").check();
  await expect(page.locator(".node-row")).toHaveCount(1);

  await page.locator("#node-favorites-only").uncheck();
  await page.locator('#row-Gnd1 [data-action="favorite"]').click();
  await page.locator("#node-favorites-only").check();
  await expect(page.locator(".node-row")).toHaveCount(0);
  await expect(page.locator("#node-count")).toHaveText("Showing 0 of 5 nodes");
});
