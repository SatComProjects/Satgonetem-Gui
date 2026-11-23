import { expect, test } from "@playwright/test";

async function openBuilder(page) {
  await page.route("**/api/experiments", async (route) => {
    await route.fulfill({ json: { ok: true, runs: [] } });
  });
  await page.goto("/experiments");
  await page.locator("#sb-toggle").click();
  await expect(page.locator("#sb-body")).toBeVisible();
}

test("scenario builder generates and extends YAML", async ({ page }) => {
  await openBuilder(page);
  await expect(page.locator(".sb-shell")).toHaveCount(1);
  await expect(page.locator(".sb-station")).toHaveCount(1);

  await page.locator("#sb-generate").click();
  await expect(page.locator("#experiment-scenario")).toHaveValue(
    /name: 'Demo Experiment'/,
  );
  await expect(page.locator("#sb-msg")).toContainText("Generated scenario YAML");

  await page.locator("#sb-add-shell").click();
  await page.locator("#sb-add-station").click();
  await expect(page.locator(".sb-shell")).toHaveCount(2);
  await expect(page.locator(".sb-station")).toHaveCount(2);

  await page.locator("#sb-generate").click();
  await expect(page.locator("#experiment-scenario")).toHaveValue(
    /- identifier: LEO2/,
  );
  await expect(page.locator("#experiment-scenario")).toHaveValue(
    /- name: Station 2/,
  );

  await page.locator('[data-action="remove-station"]').last().click();
  await expect(page.locator(".sb-station")).toHaveCount(1);
});

test("scenario builder reports validation errors and preserves collapse state", async ({
  page,
}) => {
  await openBuilder(page);
  await page.locator("#sb-generate").click();
  const generated = await page.locator("#experiment-scenario").inputValue();

  await page.locator("#sb-name").fill("");
  await page.locator("#sb-generate").click();

  await expect(page.locator("#sb-msg")).toContainText("Name is required.");
  await expect(page.locator("#experiment-scenario")).toHaveValue(generated);

  await page.locator("#sb-toggle").click();
  await expect(page.locator("#sb-body")).toBeHidden();
  await page.locator("#sb-toggle").click();
  await expect(page.locator("#sb-body")).toBeVisible();
  await expect(page.locator("#sb-name")).toHaveValue("");
});
