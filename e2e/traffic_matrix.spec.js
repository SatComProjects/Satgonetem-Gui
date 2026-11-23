import { expect, test } from "@playwright/test";

const nodes = {
  ok: true,
  nodes: [
    { name: "Gnd0", type: "ground_station", label: "Gnd0" },
    { name: "Gnd1", type: "ground_station", label: "Gnd1" },
    { name: "Sat0", type: "satellite", label: "Sat0" },
    { name: "Sat1", type: "satellite", label: "Sat1" },
  ],
};

const completed = {
  ok: true,
  job_id: "mx-1",
  status: "done",
  nodes: ["Gnd0", "Gnd1", "Sat0", "Sat1"],
  matrix: [
    [null, 10, 5, 2.5],
    [10, null, 5, 2.5],
    [5, 5, null, 1],
    [2.5, 2.5, 1, null],
  ],
  results: [
    { src: "Gnd0", dst: "Gnd1", status: "done", throughput_mbps: 10, error: null },
    { src: "Gnd0", dst: "Sat0", status: "done", throughput_mbps: 5, error: null },
    { src: "Gnd0", dst: "Sat1", status: "done", throughput_mbps: 2.5, error: null },
    { src: "Gnd1", dst: "Gnd0", status: "done", throughput_mbps: 10, error: null },
    { src: "Gnd1", dst: "Sat0", status: "done", throughput_mbps: 5, error: null },
    { src: "Gnd1", dst: "Sat1", status: "done", throughput_mbps: 2.5, error: null },
    { src: "Sat0", dst: "Gnd0", status: "done", throughput_mbps: 5, error: null },
    { src: "Sat0", dst: "Gnd1", status: "done", throughput_mbps: 5, error: null },
    { src: "Sat0", dst: "Sat1", status: "done", throughput_mbps: 1, error: null },
    { src: "Sat1", dst: "Gnd0", status: "done", throughput_mbps: 2.5, error: null },
    { src: "Sat1", dst: "Gnd1", status: "done", throughput_mbps: 2.5, error: null },
    { src: "Sat1", dst: "Sat0", status: "done", throughput_mbps: 1, error: null },
  ],
  pairs_total: 12,
  pairs_completed: 12,
  started_at: "2026-01-01T00:00:00Z",
  finished_at: "2026-01-01T00:00:10Z",
  errors: [],
};

const running = {
  ...completed,
  status: "running",
  pairs_completed: 4,
  matrix: [
    [null, 10, null, null],
    [10, null, null, null],
    [null, null, null, null],
    [null, null, null, null],
  ],
  finished_at: null,
};

test("traffic matrix runs, renders a heatmap, and exports", async ({ page }) => {
  let polls = 0;
  await page.route("**/api/traffic/nodes", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/traffic/matrix", async (route) => {
    await route.fulfill({ json: { ok: true, job_id: "mx-1" } });
  });
  await page.route("**/api/traffic/matrix/mx-1", async (route) => {
    polls += 1;
    await route.fulfill({ json: polls === 1 ? running : completed });
  });
  await page.route("**/api/traffic/matrix/mx-1/export*", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        filename: "traffic-matrix-mx-1.csv",
        content: "src,dst,throughput_mbps,status,error\nGnd0,Gnd1,10.0,done,",
        content_type: "text/csv",
      },
    });
  });

  await page.goto("/matrix");
  await expect(page.locator("#matrix-nodes option")).toHaveCount(4);
  await page.locator("#matrix-start").click();

  await expect(page.locator("#matrix-progress")).toContainText("Running");
  await expect(page.locator("#matrix-results")).toBeVisible();
  await expect(page.locator(".matrix-cell")).toHaveCount(12);
  await expect(page.locator("#matrix-summary")).toContainText("Done");
  await expect(page.locator(".matrix-cell.heat-4").first()).toContainText("10.0");

  const download = page.waitForEvent("download");
  await page.locator("#matrix-export-csv").click();
  expect((await download).suggestedFilename()).toBe("traffic-matrix-mx-1.csv");
});

test("traffic matrix surfaces start failures", async ({ page }) => {
  await page.route("**/api/traffic/nodes", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/traffic/matrix", async (route) => {
    await route.fulfill({
      status: 409,
      json: { ok: false, error: "GoNetEm is not running." },
    });
  });

  await page.goto("/matrix");
  await page.locator("#matrix-start").click();

  await expect(page.locator("#matrix-progress")).toContainText("GoNetEm");
  await expect(page.locator("#matrix-results")).toBeHidden();
});
