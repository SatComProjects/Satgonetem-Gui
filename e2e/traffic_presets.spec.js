import { expect, test } from "@playwright/test";

const nodes = {
  ok: true,
  nodes: [
    { name: "Gnd0", type: "ground_station", label: "Gnd0" },
    { name: "Gnd1", type: "ground_station", label: "Gnd1" },
    { name: "Gnd2", type: "ground_station", label: "Gnd2" },
  ],
};

const addressability = {
  ok: true,
  addressable: [],
  count: 0,
  total: 100,
  routing_refresh_required: false,
};

async function mockTraffic(page) {
  await page.route("**/api/traffic/nodes", async (route) => {
    await route.fulfill({ json: nodes });
  });
  await page.route("**/api/satellites/addressable", async (route) => {
    await route.fulfill({ json: addressability });
  });
}

test("traffic presets save, apply, swap, survive reload, and delete", async ({
  page,
}) => {
  await mockTraffic(page);
  await page.goto("/traffic");
  await expect(page.locator("#tg-src option")).toHaveCount(3);

  await page.locator("#tg-src").selectOption("Gnd0");
  await page.locator("#tg-dst").selectOption("Gnd2");
  await page.locator("#tg-tool").selectOption("ping");
  await page.locator("#tg-ping-count").fill("7");
  await page.locator("#tg-preset-name").fill("Demo ping");
  await page.locator("#tg-preset-save").click();

  await expect(page.locator("#tg-preset-msg")).toContainText(
    "Saved preset Demo ping",
  );
  await expect(
    page.locator('#tg-preset-select option[value="Demo ping"]'),
  ).toHaveCount(1);

  await page.locator("#tg-src").selectOption("Gnd1");
  await page.locator("#tg-ping-count").fill("3");
  await page.locator("#tg-preset-apply").click();

  await expect(page.locator("#tg-src")).toHaveValue("Gnd0");
  await expect(page.locator("#tg-dst")).toHaveValue("Gnd2");
  await expect(page.locator("#tg-ping-count")).toHaveValue("7");

  await page.locator("#tg-swap").click();
  await expect(page.locator("#tg-src")).toHaveValue("Gnd2");
  await expect(page.locator("#tg-dst")).toHaveValue("Gnd0");

  await page.reload();
  await expect(page.locator("#tg-src option")).toHaveCount(3);
  await expect(
    page.locator('#tg-preset-select option[value="Demo ping"]'),
  ).toHaveCount(1);

  await page.locator("#tg-preset-select").selectOption("Demo ping");
  await page.locator("#tg-preset-delete").click();
  await expect(page.locator("#tg-preset-msg")).toContainText(
    "Deleted preset Demo ping",
  );
  await expect(
    page.locator('#tg-preset-select option[value="Demo ping"]'),
  ).toHaveCount(0);
});

test("queue clone and history replay enqueue fresh items", async ({ page }) => {
  await mockTraffic(page);
  const history = {
    version: 1,
    records: [
      {
        id: "run-1",
        job_id: "job-1",
        kind: "ping",
        label: "ping Gnd0 -> Gnd1 (5)",
        payload: {
          src: "Gnd0",
          dst: "Gnd1",
          delay: 0,
          count: 5,
          timeout_sec: 1,
          interval_sec: 0.2,
          packet_size: 56,
        },
        project_name: null,
        recorded_at: "2026-01-01T00:00:00+00:00",
        started_at: null,
        finished_at: "2026-01-01T00:00:01+00:00",
        duration_ms: 1000,
        status: "done",
        results: {
          packets_transmitted: 5,
          packets_received: 5,
          packet_loss_percent: 0,
          rtt_avg_ms: 2,
        },
        summary: [],
      },
    ],
  };
  await page.addInitScript((stored) => {
    localStorage.setItem("sgnt_traffic_history", JSON.stringify(stored));
  }, history);

  await page.goto("/traffic");
  await expect(page.locator("#tg-src option")).toHaveCount(3);
  await page.locator("#tg-src").selectOption("Gnd0");
  await page.locator("#tg-dst").selectOption("Gnd1");
  await page.locator("#tg-tool").selectOption("ping");
  await page.locator("#tg-add-queue").click();

  await expect(page.locator(".queue-item")).toHaveCount(1);
  await page.locator('.queue-item [data-action="clone"]').click();
  await expect(page.locator(".queue-item")).toHaveCount(2);
  await expect(page.locator(".queue-item").nth(1)).toContainText("(copy)");

  await page.locator("#jq-history").click();
  await expect(page.locator('[data-history-action="replay"]')).toHaveCount(1);
  await page.locator('[data-history-action="replay"]').click();
  await expect(page.locator(".queue-item")).toHaveCount(3);
  await expect(page.locator(".queue-item").nth(2)).toContainText("(replay)");
  await expect(page.locator("#history-msg")).toContainText(
    "Replay added to the queue",
  );
});
