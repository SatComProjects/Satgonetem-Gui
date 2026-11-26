import { expect, test } from "@playwright/test";

test("world view releases its timers and Cesium input handler on pagehide", async ({
  page,
}) => {
  let satellitePolls = 0;
  let usagePolls = 0;
  await page.route("**/api/satellites*", async (route) => {
    satellitePolls += 1;
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/ground_stations*", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/links*", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/links/usage*", async (route) => {
    usagePolls += 1;
    await route.fulfill({ json: { available: false, links: [] } });
  });

  await page.goto("/world");

  const fallback = page.locator("#world-fallback");
  await expect
    .poll(
      async () =>
        (await fallback.isVisible()) ||
        page.evaluate(() => typeof window.Cesium === "object"),
      { timeout: 20000 },
    )
    .toBe(true);
  test.skip(await fallback.isVisible(), "WebGL is unavailable in this browser.");
  await page.waitForSelector(".cesium-widget", { timeout: 20000 });

  await page.evaluate(() => {
    window.__worldTeardown = {
      clearedTimeouts: 0,
      clearedIntervals: 0,
      destroyedHandlers: 0,
    };
    const originalClearTimeout = window.clearTimeout.bind(window);
    const originalClearInterval = window.clearInterval.bind(window);
    window.clearTimeout = (timerId) => {
      window.__worldTeardown.clearedTimeouts += 1;
      return originalClearTimeout(timerId);
    };
    window.clearInterval = (timerId) => {
      window.__worldTeardown.clearedIntervals += 1;
      return originalClearInterval(timerId);
    };
    const prototype = window.Cesium.ScreenSpaceEventHandler.prototype;
    const originalDestroy = prototype.destroy;
    prototype.destroy = function destroy() {
      window.__worldTeardown.destroyedHandlers += 1;
      return originalDestroy.call(this);
    };
  });

  // Enable link usage so the view also owns a five-second interval.
  await page.evaluate(() => {
    const checkbox = document.querySelector("#cb-link-usage");
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change"));
  });
  await page.waitForTimeout(300);

  // A bfcache pagehide must not tear the view down or consume the listener.
  await page.evaluate(() => {
    window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true }));
  });
  await page.waitForTimeout(200);
  expect(
    await page.evaluate(() => window.__worldTeardown.destroyedHandlers),
  ).toBe(0);

  await page.evaluate(() => {
    window.dispatchEvent(new Event("pagehide"));
    window.dispatchEvent(new Event("pagehide"));
  });
  const teardown = await page.evaluate(() => window.__worldTeardown);

  // Let any request already in flight reach the route handler before sampling.
  await page.waitForTimeout(500);
  const satellitesAfterTeardown = satellitePolls;
  const usageAfterTeardown = usagePolls;
  await page.waitForTimeout(5500);

  expect(satellitePolls).toBe(satellitesAfterTeardown);
  expect(usagePolls).toBe(usageAfterTeardown);
  expect(teardown.clearedTimeouts).toBeGreaterThan(0);
  expect(teardown.clearedIntervals).toBeGreaterThan(0);
  expect(teardown.destroyedHandlers).toBe(1);
});
