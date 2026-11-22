import { expect, test } from "@playwright/test";

const snapshot = {
  ok: true,
  coverage_percent: 37.5,
  satellites: 100,
  sampled_cells: 64_800,
  elevation_deg: 10,
  grid_resolution_deg: 1,
  step: 0,
  generation: 1,
  duration_ms: 82,
  cached: false,
  shells: [
    { identifier: "LEO", satellites: 100, coverage_percent: 37.5 },
  ],
  ground_stations: [
    {
      name: "Berlin",
      covered: true,
      best_satellite: "Sat0",
      best_elevation_deg: 41.2,
    },
    {
      name: "Oslo",
      covered: false,
      best_satellite: "Sat4",
      best_elevation_deg: 4.1,
    },
  ],
  shells_truncated: false,
  ground_stations_truncated: false,
};

test("coverage page analyzes and renders shells and stations", async ({ page }) => {
  let requestBody = null;
  await page.route("**/api/analysis/coverage", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ json: snapshot });
  });

  await page.goto("/coverage");
  await expect(page.locator("#coverage-empty")).toBeVisible();
  await expect(page.locator("#coverage-results")).toBeHidden();

  await page.locator("#coverage-run").click();

  await expect(page.locator("#coverage-percent")).toHaveText("37.5%");
  await expect(page.locator("#coverage-summary")).toContainText(
    "100 satellites",
  );
  await expect(page.locator("#coverage-shells-list")).toContainText("LEO");
  await expect(page.locator("#coverage-stations-table")).toContainText("Berlin");
  await expect(page.locator("#coverage-stations-table")).toContainText(
    "Covered",
  );
  await expect(page.locator("#coverage-stations-table")).toContainText("Oslo");
  await expect(page.locator("#coverage-stations-table")).toContainText(
    "Uncovered",
  );
  expect(requestBody.elevation_deg).toBe(10);
  expect(requestBody.grid_resolution_deg).toBe(1);
  expect(requestBody.include_shells).toBe(true);
  expect(requestBody.include_ground_stations).toBe(true);
});

test("coverage page surfaces a too-large grid", async ({ page }) => {
  await page.route("**/api/analysis/coverage", async (route) => {
    await route.fulfill({
      status: 422,
      json: {
        ok: false,
        error:
          "Coverage grid too large: 103,680,000 satellite-cells; choose a coarser resolution.",
      },
    });
  });

  await page.goto("/coverage");
  await page.locator("#coverage-run").click();

  await expect(page.locator("#coverage-msg")).toContainText("coarser");
  await expect(page.locator("#coverage-results")).toBeHidden();
});
