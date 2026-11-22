import { expect, test } from "@playwright/test";

const HISTORY_KEY = "sgnt_traffic_history";

function pingRecord(overrides = {}) {
  return {
    id: "run-1700000000000-j1",
    job_id: "j1",
    kind: "ping",
    label: "ping Sat0 -> Gnd100",
    payload: { src: "Sat0", dst: "Gnd100" },
    project_name: "Demo",
    recorded_at: "2026-01-02T03:04:05.000Z",
    started_at: "2026-01-02T03:03:55.000Z",
    finished_at: "2026-01-02T03:04:05.000Z",
    duration_ms: 10_000,
    status: "done",
    results: {
      packets_received: 9,
      packets_transmitted: 10,
      packet_loss_percent: 10,
      rtt_avg_ms: 24.5,
      rtt_min_ms: 21,
      rtt_max_ms: 30,
      reachable: true,
    },
    summary: [
      { label: "Loss", value: 10, unit: "%" },
      { label: "RTT avg", value: 24.5, unit: "ms" },
      { label: "RTT min", value: 21, unit: "ms" },
      { label: "RTT max", value: 30, unit: "ms" },
      { label: "Packets", value: 9, unit: "" },
    ],
    ...overrides,
  };
}

function iperf3Record(overrides = {}) {
  return {
    id: "run-1700000002000-i1",
    job_id: "i1",
    kind: "iperf3",
    label: "iperf3 Sat0 -> Gnd100",
    payload: { src: "Sat0", dst: "Gnd100" },
    project_name: "Demo",
    recorded_at: "2026-01-02T03:06:05.000Z",
    started_at: "2026-01-02T03:05:55.000Z",
    finished_at: "2026-01-02T03:06:05.000Z",
    duration_ms: 10_000,
    status: "done",
    results: {
      protocol: "TCP",
      avg_throughput_mbps: 100,
      intervals: [
        { sum: { seconds: 1, bits_per_second: 100_000_000 } },
        { sum: { seconds: 1, bits_per_second: 120_000_000 } },
      ],
    },
    summary: [
      { label: "Avg throughput", value: 100, unit: "Mbps" },
      { label: "Avg RTT", value: 18, unit: "ms" },
    ],
    ...overrides,
  };
}

async function seedHistory(page, records) {
  await page.addInitScript(
    ({ key, value }) => {
      localStorage.setItem(key, JSON.stringify({ version: 1, records: value }));
    },
    { key: HISTORY_KEY, value: records },
  );
}

async function openHistory(page) {
  await page.goto("/");
  await page.locator("#jq-toggle").click();
  await expect(page.locator("#jq-history")).toBeVisible();
  await page.locator("#jq-history").click();
  await expect(page.locator("#results-modal")).toBeVisible();
}

test("history reopens a stored ping run in the results modal", async ({ page }) => {
  await seedHistory(page, [pingRecord()]);

  await openHistory(page);
  await expect(page.locator("#results-title")).toHaveText("Experiment History");
  await expect(page.locator("#history-count")).toHaveText("1 run");
  await expect(page.locator(".history-row")).toHaveCount(1);

  const row = page.locator(".history-row").first();
  await expect(row.locator(".history-kind")).toHaveText("ping");
  await expect(row.locator(".history-endpoints")).toHaveText("Sat0 → Gnd100");
  await expect(row.locator(".history-summary")).toContainText("24.5 ms");
  await expect(page.locator(".history-empty")).toBeHidden();

  await row.locator('[data-history-action="open"]').click();

  await expect(page.locator("#results-title")).toHaveText(
    "Ping Results - Sat0 -> Gnd100",
  );
  await expect(page.locator("#results-body")).toContainText("RTT avg");
  await expect(page.locator("#results-body")).toContainText("24.50 ms");
});

test("a done job is recorded with its project name", async ({ page }) => {
  await page.route("**/api/traffic/ping", async (route) => {
    await route.fulfill({ json: { ok: true, job_id: "job-live-1" } });
  });
  await page.route("**/api/traffic/status**", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        status: "done",
        results: {
          packets_received: 9,
          packets_transmitted: 10,
          packet_loss_percent: 10,
          rtt_avg_ms: 24.5,
          rtt_min_ms: 21,
          rtt_max_ms: 30,
          reachable: true,
        },
      },
    });
  });
  await page.route("**/api/project/status", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        state: "loaded",
        project_name: "History Demo",
        loaded: true,
      },
    });
  });

  await page.goto("/traffic");
  await page.waitForLoadState("networkidle");
  const queueUrl = await page.evaluate(() => {
    const script = document.querySelector('script[src*="/static/queue.js"]');
    return script ? script.getAttribute("src") : "/static/queue.js";
  });
  await page.evaluate(async (url) => {
    const queue = await import(url);
    queue.jqAdd({
      kind: "ping",
      payload: { src: "Sat0", dst: "Gnd100" },
      label: "capture ping",
      delay: 0,
    });
  }, queueUrl);

  await page.locator('[data-action="start"]').click();
  await expect(page.locator(".queue-status")).toHaveText("done");

  await expect
    .poll(async () =>
      page.evaluate(() => {
        const history = JSON.parse(
          localStorage.getItem("sgnt_traffic_history") || "null",
        );
        return history?.records?.[0]?.project_name ?? null;
      }),
    )
    .toBe("History Demo");

  await expect(page.locator("#jq-history")).toBeVisible();
  await page.locator("#jq-history").click();
  await expect(page.locator(".history-row")).toHaveCount(1);
  await expect(page.locator(".history-summary")).toContainText("24.5 ms");
  await expect(page.locator(".history-when")).toContainText("History Demo");
});

test("history exports and deletes records", async ({ page }) => {
  await seedHistory(page, [pingRecord()]);
  await openHistory(page);

  const allDownload = page.waitForEvent("download");
  await page.locator("#history-export-json").click();
  expect((await allDownload).suggestedFilename()).toBe("sgnt-history.json");

  const csvDownload = page.waitForEvent("download");
  await page.locator("#history-export-csv").click();
  expect((await csvDownload).suggestedFilename()).toBe("sgnt-history.csv");

  const runDownload = page.waitForEvent("download");
  await page.locator('[data-history-action="export"]').click();
  expect((await runDownload).suggestedFilename()).toBe(
    "sgnt-run-run-1700000000000-j1.json",
  );

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-history-action="delete"]').click();
  await expect(page.locator(".history-row")).toHaveCount(0);
  await expect(page.locator(".history-empty")).toBeVisible();
  await expect(page.locator("#history-count")).toHaveText("0 runs");
  await expect(page.locator("#history-msg")).toContainText("Run deleted");
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("sgnt_traffic_history")).records,
    ),
  ).toEqual([]);
});

test("history compare renders one chart for the primary series", async ({ page }) => {
  await page.route("https://cdn.jsdelivr.net/**", async (route) => {
    await route.fulfill({ contentType: "application/javascript", body: "" });
  });
  await seedHistory(page, [
    iperf3Record({
      id: "run-1700000002000-i1",
      job_id: "i1",
      recorded_at: "2026-01-02T03:06:05.000Z",
    }),
    iperf3Record({
      id: "run-1700000003000-i2",
      job_id: "i2",
      recorded_at: "2026-01-02T03:07:05.000Z",
      results: {
        protocol: "TCP",
        avg_throughput_mbps: 80,
        intervals: [
          { sum: { seconds: 1, bits_per_second: 80_000_000 } },
          { sum: { seconds: 1, bits_per_second: 90_000_000 } },
        ],
      },
      summary: [
        { label: "Avg throughput", value: 80, unit: "Mbps" },
        { label: "Avg RTT", value: 22, unit: "ms" },
      ],
    }),
  ]);

  await openHistory(page);
  await page.evaluate(() => {
    window.__historyCharts = [];
    window.Chart = class {
      constructor(canvas, config) {
        window.__historyCharts.push({ id: canvas.id, config });
      }

      destroy() {}
    };
  });
  await page.locator(".history-select").nth(0).check();
  await page.locator(".history-select").nth(1).check();
  await page.locator("#history-compare").click();

  await expect(page.locator(".history-compare-table")).toBeVisible();
  await expect
    .poll(async () => page.evaluate(() => window.__historyCharts.length))
    .toBe(1);

  const chart = await page.evaluate(() => {
    const entry = window.__historyCharts[0];
    return {
      id: entry.id,
      labels: entry.config.data.labels,
      datasets: entry.config.data.datasets.map((dataset) => dataset.label),
    };
  });
  expect(chart).toEqual({
    id: "history-compare-chart",
    labels: [1, 2],
    datasets: ["Run A", "Run B"],
  });
});

test("history compares two same-kind runs and stays closable", async ({ page }) => {
  const older = pingRecord({
    id: "run-1700000000000-j1",
    job_id: "j1",
    recorded_at: "2026-01-02T03:04:05.000Z",
  });
  const newer = pingRecord({
    id: "run-1700000001000-j2",
    job_id: "j2",
    recorded_at: "2026-01-02T03:05:05.000Z",
    results: {
      packets_received: 10,
      packets_transmitted: 10,
      packet_loss_percent: 0,
      rtt_avg_ms: 30,
      rtt_min_ms: 25,
      rtt_max_ms: 35,
      reachable: true,
    },
    summary: [
      { label: "Loss", value: 0, unit: "%" },
      { label: "RTT avg", value: 30, unit: "ms" },
      { label: "RTT min", value: 25, unit: "ms" },
      { label: "RTT max", value: 35, unit: "ms" },
      { label: "Packets", value: 10, unit: "" },
    ],
  });
  await seedHistory(page, [older, newer]);

  await openHistory(page);
  await expect(page.locator(".history-row")).toHaveCount(2);
  await page.locator(".history-select").nth(0).check();
  await page.locator(".history-select").nth(1).check();
  await page.locator("#history-compare").click();

  await expect(page.locator(".history-compare-table")).toBeVisible();
  await expect(page.locator(".history-compare-table")).toContainText("RTT avg");
  await expect(page.locator(".history-compare-summary")).toContainText("Run A");
  await expect(page.locator(".history-compare-summary")).toContainText("Run B");
  await expect(
    page
      .locator(
        ".history-compare-delta.positive, .history-compare-delta.negative, .history-compare-delta.neutral",
      )
      .first(),
  ).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator("#results-modal")).toBeHidden();
});
