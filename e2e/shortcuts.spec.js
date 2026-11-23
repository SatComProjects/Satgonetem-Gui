import { expect, test } from "@playwright/test";

test("shell marks the active page and exposes the skip link", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('nav a[aria-current="page"]')).toHaveText(
    "Dashboard",
  );

  await page.locator(".skip-link").focus();
  await expect(page.locator(".skip-link")).toBeVisible();
});

test("keyboard shortcuts open help and navigate with g-prefix", async ({
  page,
}) => {
  await page.goto("/");

  await page.keyboard.press("Shift+Slash");
  await expect(page.locator("#shortcuts-help")).toBeVisible();
  await expect(page.locator("#shortcuts-list")).toContainText("Go to Nodes");
  await page.keyboard.press("Escape");
  await expect(page.locator("#shortcuts-help")).toBeHidden();

  await page.keyboard.press("g");
  await page.keyboard.press("n");
  await expect(page).toHaveURL(/\/nodes$/);
  await expect(page.locator('nav a[href="/nodes"]')).toHaveAttribute(
    "aria-current",
    "page",
  );

  await expect(page.locator("html")).toHaveAttribute(
    "data-shortcuts",
    "ready",
  );
  await page.keyboard.press("g");
  await page.keyboard.press("t");
  await expect(page).toHaveURL(/\/traffic$/);
});

test("shortcuts are ignored while typing or with modifiers", async ({ page }) => {
  await page.goto("/traffic");
  await page.locator("#tg-preset-name").focus();

  await page.keyboard.press("Shift+Slash");
  await expect(page.locator("#shortcuts-help")).toBeHidden();
  await expect(page.locator("#tg-preset-name")).toHaveValue("?");

  await page.keyboard.press("Control+g");
  await page.keyboard.press("w");
  await expect(page).toHaveURL(/\/traffic$/);
});

test("queue stays inside a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/traffic");
  const queue = page.locator("#floating-queue");
  await expect(queue).toBeVisible();
  const box = await queue.boundingBox();
  expect(box).not.toBeNull();
  expect(box.width).toBeLessThanOrEqual(390);
  expect(box.x).toBeGreaterThanOrEqual(0);
});
