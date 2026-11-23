import { expect, test } from "@playwright/test";

const satellites = [
  {
    id: 0,
    name: "Sat0",
    position: { latitude: 0, longitude: 0, altitude: 550 },
  },
  {
    id: 1,
    name: "Sat1",
    position: { latitude: 1, longitude: 1, altitude: 550 },
  },
];

const groundStations = [
  {
    id: 100,
    name: "Gnd0",
    city: "Berlin",
    position: { latitude: 52.5, longitude: 13.4, altitude: 0 },
  },
];

const links = [
  {
    src: "Sat0",
    dst: "Sat1",
    type: "InterSatelliteLink",
    direction: "undefined",
    distance_km: 157,
    delay_ms: 0.5,
    capacity_kbps: 100000,
    is_active: true,
  },
  {
    src: "Gnd0",
    dst: "Sat0",
    type: "GroundStationLink",
    direction: "undefined",
    distance_km: 1200,
    delay_ms: 4,
    capacity_kbps: 100000,
    is_active: true,
  },
];

test("world deep link opens the node inspector and isolation toggle", async ({
  page,
}) => {
  await page.route("**/api/satellites*", async (route) => {
    await route.fulfill({ json: satellites });
  });
  await page.route("**/api/ground_stations*", async (route) => {
    await route.fulfill({ json: groundStations });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: links });
  });

  await page.goto("/world?node=Sat0");

  const fallback = page.locator("#world-fallback");
  const inspector = page.locator("#world-inspector");
  await expect
    .poll(
      async () => (await fallback.isVisible()) || (await inspector.isVisible()),
      { timeout: 20000 },
    )
    .toBe(true);
  test.skip(await fallback.isVisible(), "WebGL is unavailable in this browser.");

  await expect(inspector).toBeVisible();
  await expect(page.locator("#world-inspector-title")).toHaveText("Sat0");
  await expect(page.locator("#world-inspector-kind")).toHaveText("Satellite");
  await expect(page.locator("#world-inspector-links")).toContainText("2 links");
  await expect(page.locator("#world-inspector-neighbors")).toContainText("Sat1");
  await expect(page.locator("#world-inspector-peers")).toContainText("Sat1");

  await page.locator("#world-isolate-links").check();
  await expect(page.locator("#world-isolate-links")).toBeChecked();

  await page.locator("#world-inspector-close").click();
  await expect(inspector).toBeHidden();
  await expect(page.locator("#world-isolate-links")).not.toBeChecked();
});
