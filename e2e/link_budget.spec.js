import { expect, test } from "@playwright/test";

const result = {
  ok: true,
  capacity_kbps: 2500,
  capacity_mbps: 2.5,
  eirp_db: 44.12,
  g_over_t_db: 17.46,
  fspl_db: 178.9,
  atmospheric_db: 0.4,
  atmospheric_available: true,
  cn0_dbhz: 94.2,
  cn_db: 7.1,
  direction: "downlink",
  strategy: "shannon",
  frequency_ghz: 19,
  bandwidth_mhz: 500,
  distance_km: 1000,
  elevation_deg: 30,
};

test("link budget calculates and renders the breakdown", async ({ page }) => {
  let requestBody = null;
  await page.route("**/api/analysis/link-budget", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ json: result });
  });

  await page.goto("/link-budget");
  await expect(page.locator("#lb-empty")).toBeVisible();
  await expect(page.locator("#lb-results")).toBeHidden();

  await page.locator("#lb-direction").selectOption("uplink");
  await expect(page.locator("#lb-frequency")).toHaveValue("14.25");
  await page.locator("#lb-run").click();

  await expect(page.locator("#lb-capacity")).toHaveText("2.5 Mbps");
  await expect(page.locator("#lb-summary")).toContainText("Shannon");
  await expect(page.locator("#lb-breakdown")).toContainText("C/N\u2080");
  await expect(page.locator("#lb-breakdown")).toContainText("178.90 dB");
  await expect(page.locator("#lb-atmosphere-note")).toBeHidden();
  expect(requestBody.direction).toBe("uplink");
  expect(requestBody.frequency_ghz).toBe(14.25);
  expect(requestBody.strategy).toBe("shannon");
  expect(requestBody.bandwidth_mhz).toBe(500);
});

test("link budget surfaces validation errors", async ({ page }) => {
  await page.route("**/api/analysis/link-budget", async (route) => {
    await route.fulfill({
      status: 422,
      json: { ok: false, error: "frequency_ghz must be positive" },
    });
  });

  await page.goto("/link-budget");
  await page.locator("#lb-run").click();

  await expect(page.locator("#lb-msg")).toContainText("frequency_ghz");
  await expect(page.locator("#lb-results")).toBeHidden();
  await expect(page.locator("#lb-empty")).toBeVisible();
});
