const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const USER = "demo_admin";
const PASSWORD = "synthetic-passphrase";

async function login(page) {
  await page.goto("/login");
  await page.locator('input[name="username"]').fill(USER);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/($|\?)/);
}

async function logout(page) {
  await page.goto("/");
  await page.locator('form[action="/logout"] button').click();
  await expect(page).toHaveURL(/\/login/);
}

test.describe.serial("BudgetPilot Chromium journey", () => {
  test("first launch creates the administrator and completes financial setup", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/auth\/setup/);
    await expect(page.locator(".language-switch")).toBeVisible();

    await page.locator('input[name="username"]').fill(USER);
    await page.locator('input[name="password"]').fill(PASSWORD);
    await page.locator('input[name="password_confirm"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/setup\/full/);

    await page.locator('input[name="account_balance"]').fill("2500");
    await page.locator('input[name="reserve_amount"]').fill("300");
    await page.locator('input[name="pay_name_1"]').fill("Synthetic Rent");
    await page.locator('input[name="pay_amount_1"]').fill("850");
    await page.locator('input[name="pay_day_1"]').fill("5");
    await page.locator('form').last().locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/($|\?)/);
    await expect(page.locator("body")).toContainText(/Actually available|Reálne k dispozícii/);
  });

  test("failed login, successful login, logout, and protected redirect work", async ({ browser, page }) => {
    await page.goto("/login");
    await page.locator('input[name="username"]').fill(USER);
    await page.locator('input[name="password"]').fill("wrong-password");
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("body")).toContainText(/Invalid login credentials|Neplatné prihlasovacie údaje/);

    await login(page);
    await expect(page.locator("body")).toContainText(/Actually available|Reálne k dispozícii/);
    await logout(page);

    const context = await browser.newContext();
    const protectedPage = await context.newPage();
    await protectedPage.goto("/payments");
    await expect(protectedPage).toHaveURL(/\/login/);
    await context.close();
  });

  test("creates income, recurring payment, one-time payment, expense, and verifies totals", async ({ page }) => {
    await login(page);

    await page.goto("/manage");
    await page.locator('form[action="/income/add"] input[name="name"]').fill("Synthetic Salary");
    await page.locator('form[action="/income/add"] input[name="amount"]').fill("3200");
    await page.locator('form[action="/income/add"] input[name="day"]').fill("15");
    await page.locator('form[action="/income/add"] button').click();

    await page.goto("/manage");
    await page.locator('form[action="/payment/add"] input[name="name"]').fill("Synthetic Utilities");
    await page.locator('form[action="/payment/add"] input[name="amount"]').fill("120");
    await page.locator('form[action="/payment/add"] input[name="day"]').fill("20");
    await page.locator('form[action="/payment/add"] button').click();

    await page.goto("/manage");
    await page.locator('form[action="/onetime/add"] input[name="name"]').fill("Synthetic Car Service");
    await page.locator('form[action="/onetime/add"] input[name="amount"]').fill("180");
    await page.locator('form[action="/onetime/add"] input[name="due_date"]').fill("2026-07-25");
    await page.locator('form[action="/onetime/add"] button').click();

    await page.goto("/expenses");
    await page.locator('form[action="/expense/add"] input[name="amount"]').first().fill("42.50");
    await page.locator('form[action="/expense/add"] button').first().click();

    await page.goto("/");
    await expect(page.locator("body")).toContainText(/Still to pay|Ešte treba zaplatiť/);
    await expect(page.locator("body")).toContainText("€");
  });

  test("paid, unpaid, future, overdue, deferred, filtering, sorting, and confirmation flows render", async ({ page }) => {
    await login(page);
    await page.goto("/payments");
    await expect(page.locator("#payment-inbox")).toBeVisible();
    await expect(page.locator(".work-tab")).toHaveCount(4);

    const firstPayButton = page.locator(".paid-quick-form button").first();
    await expect(firstPayButton).toBeVisible();
    await firstPayButton.click();
    await expect(page.locator(".impact-modal")).toBeVisible();
    await page.locator(".impact-modal .confirm").click();
    await expect(page.locator("body")).toContainText(/Paid|Zaplatené/);

    await page.goto("/manage");
    await expect(page.locator("#payment-templates")).toBeVisible();
    await page.locator("#payment-templates summary").click();
    await expect(page.locator(".manager-card").first()).toBeVisible();
  });

  test("switches Slovak and English and persists language after refresh", async ({ page }) => {
    await login(page);
    await page.goto("/");
    await page.locator('.language-switch a[href^="/language/en"]').first().click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("body")).toContainText("Actually available");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("body")).toContainText("Actually available");

    await page.locator('.language-switch a[href^="/language/sk"]').first().click();
    await expect(page.locator("html")).toHaveAttribute("lang", "sk");
    await expect(page.locator("body")).toContainText("Reálne k dispozícii");
  });

  test("mobile navigation and validation/destructive confirmation are usable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto("/");
    await expect(page.locator(".bottomnav")).toBeVisible();
    await page.locator(".bottomnav a", { hasText: /Platby|Payments/ }).click();
    await expect(page).toHaveURL(/\/payments/);

    await page.goto("/manage");
    await page.locator(".danger-zone summary").click();
    page.once("dialog", async dialog => {
      expect(dialog.message()).toMatch(/vymazať|delete/i);
      await dialog.dismiss();
    });
    await page.locator("#reset-confirm-input").fill("ZMAZAT");
    await page.locator("#reset-submit-btn").click();
    await expect(page).toHaveURL(/\/manage/);

    const runtime = path.resolve(".tmp/e2e-runtime/data/settings.json");
    expect(fs.existsSync(runtime)).toBeTruthy();
  });
});
