import { expect, test } from "@playwright/test";

test("satellite endpoint toggle refreshes traffic choices", async ({ page }) => {
  let enabled = false;
  const ground = { name: "Gnd100", type: "ground_station", label: "Gnd100 (Berlin)" };
  const satellite = { name: "Sat0", type: "satellite", label: "Sat0" };

  await page.route("**/api/traffic/nodes", async (route) => {
    await route.fulfill({
      json: { ok: true, nodes: enabled ? [ground, satellite] : [ground] },
    });
  });

  await page.route("**/api/satellites/addressable", async (route) => {
    if (route.request().method() === "POST") {
      enabled = Boolean(route.request().postDataJSON()?.enabled);
      await route.fulfill({
        json: {
          ok: true,
          enabled,
          updated: enabled ? 1 : 0,
          routing_refresh_required: true,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        ok: true,
        addressable: enabled ? ["Sat0"] : [],
        count: enabled ? 1 : 0,
        total: 1,
        routing_refresh_required: enabled,
      },
    });
  });

  await page.goto("/traffic");
  await expect(page.locator("#tg-satellites")).not.toBeChecked();
  await expect(page.locator("#tg-src option[value='Sat0']")).toHaveCount(0);

  await page.locator("#tg-satellites").check();

  await expect(page.locator("#tg-src option[value='Sat0']")).toHaveCount(1);
  await expect(page.locator("#tg-addressability-note")).toContainText(
    "Re-apply Addressing",
  );
});
