import { expect, test } from "@playwright/test";

const health = {
  ok: true,
  nodes: 101,
  links: 200,
  healthy: false,
  checks: [
    {
      id: "zero_capacity_links",
      severity: "warning",
      count: 2,
      message: "2 links have zero capacity",
      items: ["Sat0->Sat1", "Sat2->Sat3"],
    },
    {
      id: "isolated_nodes",
      severity: "info",
      count: 1,
      message: "1 node has no links",
      items: ["Gnd0"],
    },
    {
      id: "self_links",
      severity: "warning",
      count: 0,
      message: "No self-links",
      items: [],
    },
  ],
};

const exportEnvelope = {
  ok: true,
  filename: "topology.json",
  content: '{"schema":"satgonetem-gui.topology/1","nodes":[],"links":[]}',
  content_type: "application/json",
};

async function mockNodesPage(page) {
  await page.route("**/api/nodes", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/links", async (route) => {
    await route.fulfill({ json: [] });
  });
}

test("nodes page shows topology health and downloads an export", async ({
  page,
}) => {
  await mockNodesPage(page);
  await page.route("**/api/topology/health", async (route) => {
    await route.fulfill({ json: health });
  });
  await page.route("**/api/topology/export*", async (route) => {
    await route.fulfill({ json: exportEnvelope });
  });

  await page.goto("/nodes");

  await expect(page.locator("#topology-health-summary")).toHaveText(
    "101 nodes \u00b7 200 links \u00b7 1 warning",
  );
  await expect(page.locator(".topo-check")).toHaveCount(2);
  await expect(page.locator(".topo-check").first()).toContainText(
    "2 links have zero capacity",
  );
  await expect(page.locator(".topo-check").first()).toContainText("Warning");
  await expect(page.locator("#topology-health-empty")).toBeHidden();

  const download = page.waitForEvent("download");
  await page.locator("#topology-export-json").click();
  expect((await download).suggestedFilename()).toBe("topology.json");
  await expect(page.locator("#topology-health-msg")).toContainText(
    "Downloaded topology.json",
  );
});

test("nodes page explains that health needs a project", async ({ page }) => {
  await mockNodesPage(page);
  await page.route("**/api/topology/health", async (route) => {
    await route.fulfill({
      status: 404,
      json: { ok: false, error: "No project is currently loaded." },
    });
  });

  await page.goto("/nodes");

  await expect(page.locator("#topology-health-msg")).toContainText(
    "Load a project",
  );
  await expect(page.locator("#topology-export-json")).toBeDisabled();
});
