import { expect, test } from "@playwright/test";

const nodes = [
  { name: "Gnd100", type: "ground_station", label: "Gnd100 (Berlin)" },
  { name: "Sat0", type: "satellite", label: "Sat0" },
  { name: "Sat1", type: "satellite", label: "Sat1" },
];

const matrix = {
  ok: true,
  job_id: "c1",
  status: "done",
  nodes: ["Gnd100", "Sat0", "Sat1"],
  pair_count: 6,
  summary: { pairs: 6, reachable: 4, unreachable: 2 },
  results: [
    {
      source: "Gnd100",
      destination: "Sat0",
      reachable: true,
      packets_transmitted: 3,
      packets_received: 3,
      packet_loss_percent: 0,
      rtt_min_ms: 1,
      rtt_avg_ms: 1.5,
      rtt_max_ms: 2,
      error: null,
    },
    {
      source: "Gnd100",
      destination: "Sat1",
      reachable: false,
      packets_transmitted: 3,
      packets_received: 0,
      packet_loss_percent: 100,
      rtt_min_ms: null,
      rtt_avg_ms: null,
      rtt_max_ms: null,
      error: "no reply",
    },
    {
      source: "Sat0",
      destination: "Gnd100",
      reachable: true,
      packets_transmitted: 3,
      packets_received: 3,
      packet_loss_percent: 0,
      rtt_min_ms: 1,
      rtt_avg_ms: 1.25,
      rtt_max_ms: 2,
      error: null,
    },
    {
      source: "Sat1",
      destination: "Gnd100",
      reachable: true,
      packets_transmitted: 3,
      packets_received: 2,
      packet_loss_percent: 33.3,
      rtt_min_ms: 2,
      rtt_avg_ms: 2.5,
      rtt_max_ms: 3,
      error: null,
    },
  ],
  error: null,
  started_at: "2026-01-01T00:00:00+00:00",
  finished_at: "2026-01-01T00:00:12+00:00",
  elapsed_ms: 12_300,
};

test("connectivity page runs a matrix and exports CSV", async ({ page }) => {
  await page.route("**/api/traffic/nodes", async (route) => {
    await route.fulfill({ json: { ok: true, nodes } });
  });
  await page.route("**/api/diagnostics/connectivity", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({ json: { ok: true, job_id: "c1" } });
  });
  await page.route("**/api/diagnostics/connectivity/c1**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/export")) {
      await route.fulfill({
        json: {
          ok: true,
          filename: "connectivity-c1.csv",
          content: "source,destination,reachable\nGnd100,Sat0,true\n",
          content_type: "text/csv",
        },
      });
      return;
    }
    await route.fulfill({ json: matrix });
  });

  await page.goto("/connectivity");
  await expect(page.locator(".conn-node")).toHaveCount(3);
  await expect(page.locator("#connectivity-node-count")).toContainText(
    "3 selected",
  );
  await expect(page.locator("#connectivity-start")).toBeEnabled();

  await page.locator("#connectivity-start").click();

  await expect(page.locator(".conn-matrix tbody tr")).toHaveCount(3);
  await expect(page.locator("#connectivity-summary")).toContainText(
    "6 pairs",
  );
  await expect(page.locator("#connectivity-summary")).toContainText(
    "2 unreachable",
  );
  await expect(page.locator(".conn-cell.unreachable")).toHaveCount(1);
  await expect(page.locator("#connectivity-export-csv")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.locator("#connectivity-export-csv").click();
  expect((await download).suggestedFilename()).toBe("connectivity-c1.csv");
});
