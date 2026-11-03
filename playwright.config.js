import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    headless: true,
  },
  webServer: {
    command:
      "mkdir -p /tmp/satgonetem-playwright-save /tmp/satgonetem-playwright-mpl && " +
      "SATGONETEM_GUI_SAVE_ROOT=/tmp/satgonetem-playwright-save " +
      "SATGONETEM_GUI_PORT=8010 " +
      "MPLCONFIGDIR=/tmp/satgonetem-playwright-mpl " +
      ".venv/bin/python -m satgonetem_gui.main",
    url: "http://127.0.0.1:8010",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
