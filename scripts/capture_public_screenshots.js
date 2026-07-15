#!/usr/bin/env node
const { chromium } = require("@playwright/test");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const RUNTIME = path.join(ROOT, ".tmp", "screenshots-runtime");
const OUT = path.join(ROOT, "docs", "assets", "screenshots");
const PORT = process.env.BUDGETPILOT_SCREENSHOT_PORT || "18977";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const USER = "screenshot_admin";
const PASSWORD = "synthetic-passphrase";

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForServer() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const response = await fetch(BASE_URL);
      if (response.status < 500) return;
    } catch (_) {
      await wait(250);
    }
  }
  throw new Error(`BudgetPilot did not start at ${BASE_URL}`);
}

async function main() {
  fs.rmSync(RUNTIME, { recursive: true, force: true });
  fs.mkdirSync(RUNTIME, { recursive: true });
  fs.mkdirSync(OUT, { recursive: true });

  const server = spawn("python3", ["budgetpilot_web.py"], {
    cwd: ROOT,
    env: {
      ...process.env,
      BUDGETPILOT_HOME: RUNTIME,
      BUDGETPILOT_HOST: "127.0.0.1",
      BUDGETPILOT_PORT: PORT
    },
    stdio: ["ignore", "pipe", "pipe"]
  });

  try {
    await waitForServer();
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

    await page.goto(`${BASE_URL}/login`);
    await page.screenshot({ path: path.join(OUT, "login-page.png"), fullPage: true });

    await page.goto(`${BASE_URL}/auth/setup`);
    await page.screenshot({ path: path.join(OUT, "first-run-admin-setup.png"), fullPage: true });
    await page.locator('input[name="username"]').fill(USER);
    await page.locator('input[name="password"]').fill(PASSWORD);
    await page.locator('input[name="password_confirm"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    await page.waitForURL(/\/setup\/full/);
    await page.screenshot({ path: path.join(OUT, "first-run-financial-setup.png"), fullPage: true });
    await page.locator('input[name="account_balance"]').fill("2500");
    await page.locator('input[name="reserve_amount"]').fill("300");
    await page.locator('input[name="pay_name_1"]').fill("Synthetic Rent");
    await page.locator('input[name="pay_amount_1"]').fill("850");
    await page.locator('input[name="pay_day_1"]').fill("5");
    await page.locator('input[name="pay_name_2"]').fill("Synthetic Utilities");
    await page.locator('input[name="pay_amount_2"]').fill("120");
    await page.locator('input[name="pay_day_2"]').fill("20");
    await page.locator('form').last().locator('button[type="submit"]').click();
    await page.waitForURL(/\/($|\?)/);

    await page.goto(`${BASE_URL}/language/sk?next=/`);
    await page.waitForURL(/\/($|\?)/);
    await page.screenshot({ path: path.join(OUT, "dashboard-sk.png"), fullPage: true });

    await page.goto(`${BASE_URL}/language/en?next=/`);
    await page.waitForURL(/\/($|\?)/);
    await page.screenshot({ path: path.join(OUT, "dashboard-en.png"), fullPage: true });

    await page.goto(`${BASE_URL}/payments`);
    await page.screenshot({ path: path.join(OUT, "expense-overview-payments.png"), fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE_URL}/`);
    await page.screenshot({ path: path.join(OUT, "mobile-portrait-dashboard.png"), fullPage: true });

    const menu = page.locator(".menu-toggle");
    if (await menu.isVisible()) {
      await menu.click();
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(OUT, "mobile-navigation.png"), fullPage: true });
    }

    await browser.close();
  } finally {
    server.kill("SIGTERM");
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
