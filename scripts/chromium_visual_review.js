#!/usr/bin/env node
const { chromium } = require("@playwright/test");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const RUNTIME = path.join(ROOT, ".tmp", "chromium-review-runtime");
const OUT = path.join(ROOT, "test-results", "chromium-visual-review.json");
const PORT = process.env.BUDGETPILOT_REVIEW_PORT || "18978";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const USER = "review_admin";
const PASSWORD = "synthetic-passphrase";

const viewports = [
  ["desktop", 1440, 900],
  ["laptop", 1280, 720],
  ["tablet-portrait", 768, 1024],
  ["tablet-landscape", 1024, 768],
  ["mobile-portrait", 390, 844],
  ["mobile-landscape", 844, 390],
  ["narrow-mobile", 320, 700]
];

const routes = ["/", "/payments", "/expenses", "/envelopes", "/manage", "/deferred"];

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

async function createSyntheticAppState(page) {
  await page.goto(`${BASE_URL}/auth/setup`);
  await page.locator('input[name="username"]').fill(USER);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.locator('input[name="password_confirm"]').fill(PASSWORD);
  await page.locator('button').last().click();
  await page.waitForURL(/\/setup\/full/);

  await page.locator('input[name="account_balance"]').fill("2500");
  await page.locator('input[name="reserve_amount"]').fill("300");
  await page.locator('input[name="pay_name_1"]').fill("Synthetic Rent");
  await page.locator('input[name="pay_amount_1"]').fill("850");
  await page.locator('input[name="pay_day_1"]').fill("5");
  await page.locator('input[name="pay_name_2"]').fill("Synthetic Utilities");
  await page.locator('input[name="pay_amount_2"]').fill("120");
  await page.locator('input[name="pay_day_2"]').fill("20");
  await page.locator('form').last().locator('button').last().click();
  await page.waitForURL(/\/($|\?)/);

  await page.goto(`${BASE_URL}/expenses`);
  await page.locator('form[action="/expense/add"] input[name="amount"]').first().fill("42.50");
  await page.locator('form[action="/expense/add"] button').first().click();
  await page.waitForLoadState("networkidle");
}

async function main() {
  fs.rmSync(RUNTIME, { recursive: true, force: true });
  fs.mkdirSync(RUNTIME, { recursive: true });
  fs.mkdirSync(path.dirname(OUT), { recursive: true });

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

  const report = {
    url: BASE_URL,
    viewports: viewports.map(([name, width, height]) => ({ name, width, height })),
    routes,
    consoleErrors: [],
    failedRequests: [],
    httpFailures: [],
    horizontalOverflow: [],
    checkedAt: new Date().toISOString()
  };

  try {
    await waitForServer();
    const browser = await chromium.launch();
    const page = await browser.newPage();

    page.on("console", msg => {
      if (msg.type() === "error") report.consoleErrors.push(msg.text());
    });
    page.on("requestfailed", req => {
      report.failedRequests.push({ url: req.url(), failure: req.failure()?.errorText || "" });
    });
    page.on("response", response => {
      const status = response.status();
      if (status >= 400) report.httpFailures.push({ url: response.url(), status });
    });

    await createSyntheticAppState(page);
    await page.goto(`${BASE_URL}/language/en?next=/`);
    await page.waitForLoadState("networkidle");

    for (const [name, width, height] of viewports) {
      await page.setViewportSize({ width, height });
      for (const route of routes) {
        await page.goto(`${BASE_URL}${route}`);
        await page.waitForLoadState("networkidle");
        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          bodyScrollWidth: document.body.scrollWidth,
          innerWidth: window.innerWidth
        }));
        const maxScrollWidth = Math.max(overflow.scrollWidth, overflow.bodyScrollWidth);
        if (maxScrollWidth > overflow.innerWidth + 2) {
          report.horizontalOverflow.push({ viewport: name, route, ...overflow });
        }

        const clickableTooSmall = await page.evaluate(() => {
          return Array.from(document.querySelectorAll("a,button,input,select,summary"))
            .filter(el => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
            })
            .filter(el => {
              const rect = el.getBoundingClientRect();
              return rect.width < 32 || rect.height < 32;
            })
            .slice(0, 10)
            .map(el => ({ tag: el.tagName, text: (el.textContent || el.getAttribute("aria-label") || "").trim(), width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }));
        });
        if (clickableTooSmall.length) {
          report.horizontalOverflow.push({ viewport: name, route, smallTouchTargets: clickableTooSmall });
        }
      }
    }

    await browser.close();
  } finally {
    server.kill("SIGTERM");
    fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
  }

  console.log(JSON.stringify(report, null, 2));
  if (report.consoleErrors.length || report.failedRequests.length || report.httpFailures.length || report.horizontalOverflow.length) {
    process.exitCode = 1;
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
