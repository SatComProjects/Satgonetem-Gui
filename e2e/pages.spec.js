import { expect, test } from "@playwright/test";

import { projectPayload } from "./project.js";

const pages = [
  ["/", "Dashboard"],
  ["/nodes", "Nodes"],
  ["/traffic", "Traffic Generator"],
  ["/new_project", "Create New Project"],
  ["/ground_stations", "Select Ground Stations"],
];

for (const [path, heading] of pages) {
  test(`${path} renders without page errors`, async ({ page }) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const response = await page.goto(path);
    expect(response.ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
    await expect(page.locator("[onclick], [onchange]")).toHaveCount(0);
  });
}

test("world page shell renders", async ({ page }) => {
  const response = await page.goto("/world");
  expect(response.ok()).toBeTruthy();
  await expect(page.getByRole("heading", { name: "World View" })).toBeVisible();
});


test("queue items add and remove by stable ID", async ({ page }) => {
  await page.goto("/traffic");
  await page.waitForLoadState("networkidle");

  await page.evaluate(async () => {
    const queue = await import("/static/queue.js");
    queue.jqAdd({
      kind: "ping",
      payload: { src: "Sat0", dst: "Sat1" },
      label: "queue regression",
      delay: 0,
    });
  });

  await expect(page.locator(".queue-item")).toHaveCount(1);
  await page.locator('[data-action="remove"]').click();
  await expect(page.locator(".queue-item")).toHaveCount(0);
});


test("ground-station selections from two presets survive apply", async ({ page }) => {
  await page.goto("/ground_stations");
  await page.waitForLoadState("networkidle");
  await expect(page.locator("#station_tbody tr").first()).toBeVisible();

  await page.locator("#station_tbody input[type=checkbox]").first().check();
  await page.selectOption("#preset_select", { index: 1 });
  await page.locator("#station_tbody input[type=checkbox]").first().check();
  await page.click("#apply_btn");
  await page.waitForURL("**/new_project");

  await expect(page.locator("#gs_count_label")).toHaveText("2 station(s) selected");
});


test("edit page populates an existing project", async ({ page, request }) => {
  const name = `E2EEdit${Date.now()}`;
  const create = await request.post("/api/project/create", {
    data: projectPayload(name),
  });
  expect(create.ok()).toBeTruthy();
  await expect
    .poll(async () => {
      const response = await request.get("/api/project/status");
      return (await response.json()).state;
    })
    .toBe("loaded");

  await page.goto(`/new_project?edit=${encodeURIComponent(name)}`);
  await expect(page.locator('[name="name"]')).toHaveValue(name);
  await expect(page.locator("#ground_list")).toContainText("1 station(s)");

  await page.goto("/nodes");
  await expect(page.locator(".node-row").first()).toBeVisible();
  await page.locator(".node-row").first().click();
  await expect(page.locator(".node-detail").first()).toContainText("Position");

  await page.goto("/");
  await expect(page.locator("#val-satellites")).toHaveText("100");

  await page.goto("/traffic");
  await expect(page.locator("#tg-src option")).toHaveCount(101);
  await page.selectOption("#tg-src", "Sat0");
  await page.selectOption("#tg-dst", "Sat1");
  await page.click("#tg-add-queue");
  await expect(page.locator(".queue-item")).toHaveCount(1);
});


test("world view shows a fallback when WebGL is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (String(type).startsWith("webgl")) return null;
      return original.call(this, type, ...args);
    };
  });

  await page.goto("/world");
  await expect(page.locator("#world-fallback")).toBeVisible();
  await expect(page.locator("#world")).toBeHidden();
});
