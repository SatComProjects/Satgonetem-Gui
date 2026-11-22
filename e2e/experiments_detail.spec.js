import { expect, test } from "@playwright/test";

function runRecord({
  id,
  name,
  mode = "offline",
  status = "done",
  duration = 10,
  scenario = "name: Alpha\nduration_s: 5\n",
}) {
  return {
    run_id: id,
    name,
    mode,
    status,
    started_at: "2026-01-01T00:00:00+00:00",
    finished_at: status === "done" ? "2026-01-01T00:00:10+00:00" : null,
    scenarioText: scenario,
    summary:
      status === "done"
        ? {
            metrics: {
              sim_time_s: duration,
              samples: 2,
              avg_tx_bps: 1500,
              max_tx_bps: 2000,
              avg_rx_bps: 1200,
              max_rx_bps: 1800,
              last_errors: [],
            },
            flows: { count: 1, errors: 0 },
            connectivity: { reachable: 2, pairs: 2 },
          }
        : null,
    errors: status === "error" ? ["runner failed"] : [],
    artifacts:
      status === "done"
        ? ["scenario.yaml", "summary.json", "report.md", "metrics.jsonl"]
        : ["scenario.yaml", "errors.json"],
  };
}

const metricsPayload = {
  ok: true,
  run_id: "exp-alpha",
  total: 2,
  samples: [
    {
      sim_time_s: 0,
      links: [{ tx_bps: 100, rx_bps: 80, active: true, loss_percent: 0 }],
    },
    {
      sim_time_s: 5,
      links: [{ tx_bps: 200, rx_bps: 160, active: true, loss_percent: 2 }],
    },
  ],
};

async function mockExperiments(page, records) {
  const byId = new Map(records.map((record) => [record.run_id, record]));
  await page.route("**/api/experiments", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { ok: true, run_id: records[0].run_id } });
      return;
    }
    await route.fulfill({ json: { ok: true, runs: records } });
  });
  for (const record of records) {
    await page.route(
      `**/api/experiments/${record.run_id}`,
      async (route) => {
        await route.fulfill({ json: byId.get(record.run_id) });
      },
    );
    await page.route(
      `**/api/experiments/${record.run_id}/metrics*`,
      async (route) => {
        await route.fulfill({ json: { ...metricsPayload, run_id: record.run_id } });
      },
    );
    await page.route(
      `**/api/experiments/${record.run_id}/artifacts/scenario.yaml`,
      async (route) => {
        await route.fulfill({
          json: {
            ok: true,
            filename: "scenario.yaml",
            content: record.scenarioText,
            content_type: "text/yaml",
          },
        });
      },
    );
    await page.route(
      `**/api/experiments/${record.run_id}/artifacts/report.md`,
      async (route) => {
        await route.fulfill({
          json: {
            ok: true,
            filename: "report.md",
            content: `# Run report: ${record.name}`,
            content_type: "text/markdown",
          },
        });
      },
    );
  }
}

test("experiment detail shows metrics and compare diffs scenarios", async ({
  page,
}) => {
  const alpha = runRecord({ id: "exp-alpha", name: "Alpha" });
  const beta = runRecord({
    id: "exp-beta",
    name: "Beta",
    duration: 20,
    scenario: "name: Beta\nduration_s: 10\n",
  });
  await mockExperiments(page, [alpha, beta]);

  await page.goto("/experiments");
  await expect(page.locator(".experiment-run")).toHaveCount(2);

  await page.locator('[data-detail="exp-alpha"]').click();
  await expect(page.locator("#experiment-detail")).toBeVisible();
  await expect(page.locator("#experiment-detail-status")).toContainText("Done");
  await expect(page.locator("#experiment-detail-stats")).toContainText(
    "Simulation time",
  );
  await expect(page.locator("#experiment-detail-chart-msg")).toContainText(
    "2 metric samples",
  );
  await expect(page.locator("#experiment-detail-scenario")).toContainText(
    "duration_s: 5",
  );
  await page.locator("#experiment-detail-close").click();
  await expect(page.locator("#experiment-detail")).toBeHidden();

  await page.locator('input[data-select="exp-alpha"]').check();
  await page.locator('input[data-select="exp-beta"]').check();
  await expect(page.locator("#experiment-compare-btn")).toBeEnabled();
  await page.locator("#experiment-compare-btn").click();

  await expect(page.locator("#experiment-compare")).toBeVisible();
  await expect(page.locator("#experiment-compare-table")).toContainText(
    "Avg TX",
  );
  await expect(page.locator("#experiment-compare-diff")).toContainText(
    "duration_s: 10",
  );
  await expect(
    page
      .locator("#experiment-compare-diff .diff-remove")
      .filter({ hasText: "duration_s: 5" }),
  ).toContainText("duration_s: 5");
});

test("comparison selection stops at four runs", async ({ page }) => {
  const records = Array.from({ length: 5 }, (_, index) =>
    runRecord({ id: `exp-${index}`, name: `Run ${index}` }),
  );
  await mockExperiments(page, records);

  await page.goto("/experiments");
  for (const record of records.slice(0, 4)) {
    await page.locator(`input[data-select="${record.run_id}"]`).check();
  }
  await expect(page.locator("#experiment-selection-count")).toHaveText(
    "4 selected",
  );

  const fifth = page.locator('input[data-select="exp-4"]');
  await fifth.click();
  await expect(fifth).not.toBeChecked();
  await expect(page.locator("#experiments-msg")).toContainText(
    "Select at most 4 runs",
  );
});
