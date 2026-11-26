import { expect, test } from "@playwright/test";

test("world view releases its timers and Cesium input handler on pagehide", async ({
  page,
}) => {
  let satellitePolls = 0;
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

  await page.evaluate(() => {
    window.__worldTeardown = { clearedTimers: 0, destroyedHandlers: 0 };
    const originalClearTimeout = window.clearTimeout.bind(window);
    const originalClearInterval = window.clearInterval.bind(window);
    window.clearTimeout = (timerId) => {
      window.__worldTeardown.clearedTimers += 1;
      return originalClearTimeout(timerId);
    };
    window.clearInterval = (timerId) => {
      window.__worldTeardown.clearedTimers += 1;
      return originalClearInterval(timerId);
    };
    const prototype = window.Cesium.ScreenSpaceEventHandler.prototype;
    const originalDestroy = prototype.destroy;
    prototype.destroy = function destroy() {
      window.__worldTeardown.destroyedHandlers += 1;
      return originalDestroy.call(this);
    };
  });

  // Let the 2-second poll loop settle so its next timeout is scheduled.
  await page.waitForTimeout(2500);

  await page.evaluate(() => {
    window.dispatchEvent(new Event("pagehide"));
    window.dispatchEvent(new Event("pagehide"));
  });
  const teardown = await page.evaluate(() => window.__worldTeardown);

  // Let any request already in flight reach the route handler before sampling.
  await page.waitForTimeout(500);
  const pollsAfterTeardown = satellitePolls;
  await page.waitForTimeout(2500);

  expect(satellitePolls).toBe(pollsAfterTeardown);
  expect(teardown.clearedTimers).toBeGreaterThan(0);
  expect(teardown.destroyedHandlers).toBe(1);
});
