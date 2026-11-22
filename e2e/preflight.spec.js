import { expect, test } from "@playwright/test";

const readyChecks = [
  {
    id: "storage",
    label: "Project storage",
    status: "ok",
    message: "Writable with 20.0 GiB free.",
  },
  {
    id: "docker",
    label: "Docker daemon",
    status: "warning",
    message: "Docker is not reachable.",
    hint: "Start Docker and confirm socket access.",
  },
  {
    id: "images",
    label: "Container images",
    status: "ok",
    message: "All 5 required images are available locally.",
  },
  {
    id: "gonetem",
    label: "GoNetEm server",
    status: "ok",
    message: "GoNetEm is reachable at localhost:10110.",
  },
];

const preflightPayload = {
  ok: true,
  blocking: false,
  checks: readyChecks,
  estimate: {
    satellites: 100,
    ground_stations: 1,
    containers: 101,
    estimated_memory_mb: 12928,
    note: "Rough estimate only.",
    warnings: [],
  },
};

async function seedGroundObject(page) {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      "satgonetem_gs_pending",
      JSON.stringify([
        {
          index: 0,
          name: "Berlin",
          latitude: 52.5,
          longitude: 13.4,
          elevation_m: 34,
        },
      ]),
    );
  });
}

test("dashboard shows readiness checks and warnings", async ({ page }) => {
  await page.route("**/api/diagnostics/preflight", async (route) => {
    await route.fulfill({ json: preflightPayload });
  });

  await page.goto("/");
  await expect(page.locator("#preflight-card")).toBeVisible();
  await expect(page.locator(".preflight-check")).toHaveCount(4);
  await expect(page.locator('[data-status="warning"]')).toContainText(
    "Docker is not reachable.",
  );
  await expect(page.locator("#preflight-msg")).toContainText("1 warning");
});

test("new project shows the estimate before building", async ({ page }) => {
  await page.route("**/api/diagnostics/preflight", async (route) => {
    await route.fulfill({ json: preflightPayload });
  });

  await page.goto("/new_project");
  await expect(page.locator("#preflight-panel")).toBeVisible();
  await expect(page.locator("#preflight-estimate")).toContainText(
    "100 satellites",
  );
  await expect(page.locator("#preflight-estimate")).toContainText(
    "101 containers",
  );
  await expect(page.locator(".preflight-check")).toHaveCount(4);
});

test("a blocking preflight stops project creation", async ({ page }) => {
  let createCalled = false;
  await page.route("**/api/diagnostics/preflight", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        blocking: true,
        checks: [
          {
            id: "storage",
            label: "Project storage",
            status: "error",
            message: "The save directory is not writable.",
            hint: "Set a writable save root.",
          },
        ],
        estimate: preflightPayload.estimate,
      },
    });
  });
  await page.route("**/api/project/create", async (route) => {
    createCalled = true;
    await route.fulfill({ json: { ok: true } });
  });

  await seedGroundObject(page);
  await page.goto("/new_project");
  await expect(page.locator("#preflight-msg")).toContainText("Blocked");
  await page.locator("#add_ground_btn").click();
  await expect(page.locator("#ground_list li")).toHaveCount(1);
  await page.locator("#createBtn").click();
  await expect(page.locator("#preflight-msg")).toContainText("Blocked");
  expect(createCalled).toBe(false);
});

test("build progress uses a real phase and indeterminate bar", async ({ page }) => {
  await page.route("**/api/diagnostics/preflight", async (route) => {
    await route.fulfill({ json: preflightPayload });
  });
  await page.route("**/api/project/create", async (route) => {
    await route.fulfill({ json: { ok: true } });
  });
  await page.route("**/api/project/status", async (route) => {
    await route.fulfill({
      json: {
        state: "creating",
        operation: "create",
        project_name: null,
        pending_name: "ProgressDemo",
        loaded: false,
        error: null,
        phase: "building",
        progress: null,
        started_at: "2026-01-01T00:00:00+00:00",
        finished_at: null,
        elapsed_ms: 12_300,
      },
    });
  });

  await seedGroundObject(page);
  await page.goto("/new_project");
  await expect(page.locator("#preflight-estimate")).toContainText(
    "100 satellites",
  );
  await page.locator("#add_ground_btn").click();
  await expect(page.locator("#ground_list li")).toHaveCount(1);
  await page.locator("#createBtn").click();

  await expect(page.locator("#create-status")).toBeVisible();
  await expect(page.locator("#create-progress-label")).toHaveText(
    "Building topology",
  );
  await expect(page.locator("#create-progress-fill")).toHaveClass(
    /indeterminate/,
  );
  await expect(page.locator("#create-progress-text")).toHaveText("12.3 s");
});
