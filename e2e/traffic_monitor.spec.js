import { expect, test } from "@playwright/test";

const usage = {
  ok: true,
  available: true,
  sampled_at: "2026-01-01T00:00:00Z",
  note: "",
  links: [
    {
      src: "Sat0",
      dst: "Sat1",
      type: "InterSatelliteLink",
      value_bps: 1_000_000,
      capacity_kbps: 100000,
      utilization: 1.0,
    },
    {
      src: "Gnd0",
      dst: "Sat0",
      type: "GroundStationLink",
      value_bps: 500_000,
      capacity_kbps: 50000,
      utilization: 1.0,
    },
  ],
};

const links = [
  {
    src: "Sat0",
    dst: "Sat1",
    type: "InterSatelliteLink",
    delay_ms: 1.2,
    capacity_kbps: 100000,
    loss_percent: 0.5,
    jitter_ms: 3,
    is_active: true,
  },
  {
    src: "Gnd0",
    dst: "Sat0",
    type: "GroundStationLink",
    delay_ms: 4.2,
    capacity_kbps: 50000,
    loss_percent: 0,
    jitter_ms: 0,
    is_active: true,
  },
];

const status = { current_step: 7, current_time: "2026-01-01T00:00:05Z" };

test("traffic monitor samples, pauses, exports, and clears", async ({ page }) => {
  let usageCalls = 0;
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: links });
  });
  await page.route("**/api/status", async (route) => {
    await route.fulfill({ json: status });
  });
  await page.route("**/api/links/usage", async (route) => {
    usageCalls += 1;
    await route.fulfill({ json: usage });
  });

  await page.goto("/monitor");
  await expect(page.locator("#monitor-summary")).toContainText("step 7");
  await expect(page.locator("#monitor-links-table")).toContainText("Sat0");
  await expect(page.locator("#monitor-links-table")).toContainText("1.0 Mbps");
  await expect(page.locator("#monitor-nodes-table")).toContainText("Sat0");

  await page.waitForTimeout(150);
  const beforePause = usageCalls;
  await page.locator("#monitor-pause").click();
  await expect(page.locator("#monitor-pause")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.waitForTimeout(2400);
  expect(usageCalls).toBe(beforePause);

  await page.locator("#monitor-pause").click();
  await expect
    .poll(() => usageCalls, { timeout: 5000 })
    .toBeGreaterThan(beforePause);

  const download = page.waitForEvent("download");
  await page.locator("#monitor-export-csv").click();
  expect((await download).suggestedFilename()).toBe("traffic-monitor.csv");

  await page.locator("#monitor-clear").click();
  await expect(page.locator("#monitor-links-empty")).toBeVisible();
  await expect(page.locator("#monitor-nodes-empty")).toBeVisible();
});

test("traffic monitor reports unavailable usage", async ({ page }) => {
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: links });
  });
  await page.route("**/api/status", async (route) => {
    await route.fulfill({ json: status });
  });
  await page.route("**/api/links/usage", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        available: false,
        sampled_at: null,
        note: "GoNetEm containers are stopped; link usage is unavailable.",
        links: [],
      },
    });
  });

  await page.goto("/monitor");

  await expect(page.locator("#monitor-note")).toContainText(
    "containers are stopped",
  );
  await expect(page.locator("#monitor-links-empty")).toBeVisible();
  await expect(page.locator("#monitor-links-table")).not.toContainText("Sat0");
});
