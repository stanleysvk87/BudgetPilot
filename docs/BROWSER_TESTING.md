# Browser Testing

BudgetPilot uses Playwright with Chromium for end-to-end and visual review.
The tests use isolated synthetic data under `.tmp/` and do not touch the
default local `data/` directory.

## Dependencies

Install Node dependencies:

```bash
npm install
```

Install the Chromium browser binary used by Playwright:

```bash
npx playwright install chromium
```

Chromium is installed by Playwright into the user's Playwright cache, not into
the repository.

## Commands

Run headless end-to-end tests:

```bash
npm run test:e2e
```

Run headed end-to-end tests:

```bash
npm run test:e2e:headed
```

Run the automated viewport/console/network visual review:

```bash
npm run review:chromium
```

Capture sanitized public screenshots from synthetic data:

```bash
npm run screenshots:public
```

Screenshots are written to `docs/assets/screenshots/`.

## Environment Variables

- `BUDGETPILOT_E2E_PORT` - optional port for `npm run test:e2e`
  (default `18976`).
- `BUDGETPILOT_REVIEW_PORT` - optional port for `npm run review:chromium`
  (default `18978`).
- `BUDGETPILOT_SCREENSHOT_PORT` - optional port for public screenshot capture
  (default `18977`).

Each command sets its own `BUDGETPILOT_HOME` under `.tmp/`.

## Cleanup

Generated local browser-test data can be removed with:

```bash
rm -rf .tmp test-results playwright-report
```

Do not put real financial data into browser-test screenshots. The screenshot
script starts an isolated instance, creates a synthetic administrator and
synthetic payment data, and captures pages before any password field is filled.

## Visual Regression Support

The lightweight review currently checks:

- desktop, laptop, tablet portrait, tablet landscape, mobile portrait, mobile
  landscape, and narrow mobile widths;
- horizontal overflow;
- visible clickable elements below the minimum target size;
- JavaScript console errors;
- failed browser requests;
- HTTP 4xx/5xx responses.

The stable screenshot set in `docs/assets/screenshots/` can be reviewed in
pull requests. If stricter pixel baselines are added later, keep the suite
small and deterministic: login, dashboard, payment list, and mobile dashboard.
