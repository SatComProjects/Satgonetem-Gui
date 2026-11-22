import { expect, test } from "@playwright/test";

const nodes = [
  { name: "Gnd100", type: "ground_station", id: 100, city: "Berlin", position: {} },
  { name: "Sat0", type: "satellite", id: 0, position: {} },
];

const links = [
  {
    src: "Gnd100",
    dst: "Sat0",
    type: "GroundStationLink",
    direction: "",
    distance_km: 1000,
    delay_ms: 3.34,
    capacity_kbps: 100000,
    is_active: true,
  },
  {
    src: "Sat0",
    dst: "Sat1",
    type: "InterSatelliteLink",
    direction: "ORBITAL",
    distance_km: 4000,
    delay_ms: 13.34,
    capacity_kbps: 1000000,
    is_active: false,
  },
];

const satelliteDetail = {
  ok: true,
  node: {
    name: "Sat0",
    type: "satellite",
    id: 0,
    position: { latitude: 0, longitude: 0, altitude: 550 },
    interfaces: [],
    loopback: { ipv4: "10.0.0.1" },
    routing_table: [],
    default_qos_is_on: false,
    program_specific_qos_is_on: false,
    addressable: false,
  },
};

test("node detail renders link delay, capacity, and state", async ({ page }) => {
  await page.route("**/api/nodes?*", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/nodes/Sat0", async (route) => {
    await route.fulfill({ json: satelliteDetail });
  });
  await page.route("**/api/links?*", async (route) => {
    await route.fulfill({ json: links });
  });

  await page.goto("/nodes");
  await expect(page.locator("#row-Sat0")).toBeVisible();
  await page.locator("#row-Sat0").click();

  const table = page.locator("#detail-Sat0 .link-table");
  await expect(table).toBeVisible();
  await expect(table.locator("tbody tr")).toHaveCount(2);
  await expect(table).toContainText("Gnd100");
  await expect(table).toContainText("GSL");
  await expect(table).toContainText("100 Mbps");
  await expect(table).toContainText("1 Gbps");
  await expect(table).toContainText("Inactive");
  await expect(table.locator(".link-inactive")).toHaveCount(1);
});
