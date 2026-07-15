const { defineConfig, devices } = require("@playwright/test");

const PORT = process.env.BUDGETPILOT_E2E_PORT || "18976";
const BASE_URL = `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer: {
    command: `rm -rf .tmp/e2e-runtime && mkdir -p .tmp/e2e-runtime && BUDGETPILOT_HOME="$PWD/.tmp/e2e-runtime" BUDGETPILOT_HOST=127.0.0.1 BUDGETPILOT_PORT=${PORT} python3 budgetpilot_web.py`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 30_000
  }
});
