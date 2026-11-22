import { expect, test } from "@playwright/test";

const projects = [
  {
    id: "aaaaaaaaaaaaaaaa",
    name: "Demo",
    filename: "Demo.json",
    modified_at: "2026-01-02T03:04:05+00:00",
    size_bytes: 2048,
    satellites: 100,
    ground_stations: 1,
    shells: 1,
    valid: true,
  },
  {
    id: "bbbbbbbbbbbbbbbb",
    name: "Copy",
    filename: "Copy.json",
    modified_at: "2026-01-02T03:05:05+00:00",
    size_bytes: 4096,
    satellites: 282,
    ground_stations: 3,
    shells: 2,
    valid: true,
  },
];

async function stubProjects(page) {
  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({ json: { ok: true, projects, warnings: [] } });
  });
  await page.route("**/api/project/status", async (route) => {
    await route.fulfill({
      json: {
        state: "idle",
        operation: null,
        project_name: null,
        pending_name: null,
        loaded: false,
        error: null,
        phase: "idle",
        progress: null,
        started_at: null,
        finished_at: null,
        elapsed_ms: null,
      },
    });
  });
}

test("projects page lists workspace files and opens one by id", async ({ page }) => {
  let opened = false;
  await stubProjects(page);
  await page.route("**/api/projects/aaaaaaaaaaaaaaaa/load", async (route) => {
    opened = true;
    await route.fulfill({ json: { ok: true, name: "Demo" } });
  });

  await page.goto("/projects");
  await expect(page.locator(".project-row")).toHaveCount(2);
  await expect(page.locator(".project-name").first()).toHaveText("Demo");
  await expect(page.locator(".project-row").first()).toContainText("100");
  await expect(page.locator(".project-row").first()).toContainText("2 KB");
  await expect(page.locator("#projects-empty")).toBeHidden();

  await page.locator('[data-project-action="open"]').first().click();
  await page.waitForURL("**/");
  expect(opened).toBe(true);
});

test("projects page saves the current project to the workspace", async ({ page }) => {
  let savedBody = null;
  await stubProjects(page);
  await page.route("**/api/project/save-to", async (route) => {
    savedBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        ok: true,
        id: "cccccccccccccccc",
        name: savedBody.name,
        filename: `${savedBody.name}.json`,
        overwritten: false,
      },
    });
  });

  await page.goto("/projects");
  await page.locator("#save-current-name").fill("Saved Demo");
  await page.locator("#save-current-btn").click();

  await expect(page.locator("#save-current-msg")).toHaveText(
    "Saved to workspace.",
  );
  expect(savedBody).toEqual({ name: "Saved Demo", overwrite: false });
});

test("projects page supports save in place", async ({ page }) => {
  let called = false;
  await stubProjects(page);
  await page.route("**/api/project/save-in-place", async (route) => {
    called = true;
    await route.fulfill({
      json: {
        ok: true,
        id: "aaaaaaaaaaaaaaaa",
        name: "Demo",
        filename: "Demo.json",
        overwritten: true,
      },
    });
  });

  await page.goto("/projects");
  await page.locator("#save-in-place-btn").click();

  await expect(page.locator("#save-current-msg")).toHaveText(
    "Current workspace file updated.",
  );
  expect(called).toBe(true);
});
