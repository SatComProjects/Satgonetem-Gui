import { expect, test } from "@playwright/test";

const finishedRun = {
  run_id: "exp-20260101T000000Z-abcdef12",
  name: "Api Experiment",
  mode: "offline",
  status: "done",
  started_at: "2026-01-01T00:00:00+00:00",
  finished_at: "2026-01-01T00:00:12+00:00",
  summary: { flows: { count: 2, errors: 0 } },
  errors: [],
  artifacts: ["scenario.yaml", "summary.json", "provenance.json"],
};

test("experiments page runs a scenario and downloads an artifact", async ({
  page,
}) => {
  let runs = [];
  await page.route("**/api/experiments", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.mode).toBe("offline");
      expect(body.scenario_yaml).toContain("name:");
      await route.fulfill({ json: { ok: true, run_id: finishedRun.run_id } });
      return;
    }
    await route.fulfill({ json: { ok: true, runs } });
  });
  await page.route(
    `**/api/experiments/${finishedRun.run_id}/artifacts/summary.json`,
    async (route) => {
      await route.fulfill({
        json: {
          ok: true,
          filename: "summary.json",
          content: '{"flows": {"count": 2}}',
          content_type: "application/json",
        },
      });
    },
  );
  await page.route(`**/api/experiments/${finishedRun.run_id}`, async (route) => {
    runs = [finishedRun];
    await route.fulfill({ json: finishedRun });
  });

  await page.goto("/experiments");
  await expect(page.locator("#experiment-scenario")).not.toHaveValue("");
  await expect(page.locator("#experiments-empty")).toBeVisible();

  await page.locator("#experiment-run").click();
  await expect(page.locator(".experiment-run")).toHaveCount(1);
  await expect(page.locator(".experiment-name")).toHaveText("Api Experiment");
  await expect(page.locator(".experiment-status")).toHaveText("Done");

  const download = page.waitForEvent("download");
  await page.locator('[data-artifact="summary.json"]').click();
  expect((await download).suggestedFilename()).toBe("summary.json");
});
