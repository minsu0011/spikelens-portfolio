import { expect, test } from "@playwright/test";

const password = "SpikeLens-Test-Only-7264!";

test("real full-stack user journey: registration, login, events, upload, Celery results, logout", async ({ page }) => {
  const email = `browser-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Make every event visible." })).toBeVisible();
  await expect(page.getByText("SYNTHETIC DEMO", { exact: true })).toBeVisible();
  await page.goto("/register");
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Browser Researcher");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "계정 만들기" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/login");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto("/events");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  const ticker = await page.locator("tbody .symbol-link").first().innerText();
  await page.getByRole("textbox", { name: "Ticker", exact: true }).fill(ticker);
  await page.getByRole("button", { name: "필터 적용" }).click();
  await expect(page.locator("tbody .symbol-link").first()).toHaveText(ticker);
  await page.locator("tbody .symbol-link").first().click();
  await expect(page.getByRole("heading", { name: "Observed price path" })).toBeVisible();
  await expect(page.getByText("SYNTHETIC EVENT", { exact: true })).toBeVisible();

  await page.goto("/upload");
  const suffix = Date.now().toString().slice(-6);
  const csv = "ticker,event_time,session,p0_price,t5_price,volume,price_path\n" +
    `E${suffix},2025-01-15T14:35:00Z,RTH,40,42,95000,40;40.2;40.7;41.1;41.7;42\n` +
    `F${suffix},2025-01-15T10:10:00Z,PREMARKET,18,17.1,43000,18;17.9;17.6;17.4;17.2;17.1\n`;
  await page.getByLabel("CSV file").setInputFiles({ name: `browser-${suffix}.csv`, mimeType: "text/csv", buffer: Buffer.from(csv) });
  const uploaded = page.waitForResponse((response) => response.url().endsWith("/api/v1/uploads") && response.request().method() === "POST");
  await page.getByRole("button", { name: "파일 검증 및 업로드" }).click();
  const uploadResponse = await uploaded;
  expect(uploadResponse.ok()).toBe(true);
  await expect(page.getByRole("heading", { name: /업로드 검증 결과/ })).toBeVisible();
  const created = page.waitForResponse((response) => response.url().endsWith("/api/v1/analyses") && response.request().method() === "POST");
  await page.getByRole("button", { name: "데모 분석 시작", exact: true }).click();
  const createResponse = await created;
  expect(createResponse.ok()).toBe(true);
  const job = await createResponse.json();
  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));
  await expect(page.getByText("SUCCEEDED", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("progressbar", { name: "Analysis progress" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "CSV 다운로드" })).toBeVisible();
  await page.screenshot({ path: "test-results/analysis-results.png", fullPage: true });
  expect(browserErrors).toEqual([]);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/jobs");
  await expect(page.getByRole("heading", { name: "나만의 분석 워크스페이스" })).toBeVisible();
});

test("event explorer provides empty and missing-event states; responsive navigation works", async ({ page }) => {
  await page.goto("/events");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByRole("textbox", { name: "Ticker", exact: true }).fill("ZZZNOMATCH");
  await page.getByRole("button", { name: "필터 적용" }).click();
  await expect(page.getByRole("heading", { name: "조건에 맞는 이벤트가 없습니다" })).toBeVisible();
  await page.goto("/events/00000000-0000-0000-0000-000000000000");
  await expect(page.getByRole("alert")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("link", { name: "Event explorer", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Event explorer", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/mobile-events.png", fullPage: true });
});

test("SSE interruption falls back to actual job polling and stored results", async ({ page }) => {
  const unique = Date.now().toString();
  await page.goto("/register");
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Polling Observer");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(`polling-${unique}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "계정 만들기" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/upload");
  const ticker = `P${unique.slice(-7)}`;
  const start = Date.parse("2025-01-15T14:30:00Z");
  const rows = Array.from({ length: 2000 }, (_, index) =>
    `${ticker},${new Date(start + index * 1000).toISOString()},RTH,40,42,95000,40;41;42`);
  const csv = "ticker,event_time,session,p0_price,t5_price,volume,price_path\n" + rows.join("\n") + "\n";
  await page.getByLabel("CSV file").setInputFiles({ name: `polling-${unique}.csv`, mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "파일 검증 및 업로드" }).click();
  await expect(page.getByRole("heading", { name: /업로드 검증 결과/ })).toBeVisible();
  let streamAttempts = 0;
  let stateRequests = 0;
  await page.route("**/api/v1/jobs/*/stream", (route) => { streamAttempts += 1; return route.abort("failed"); });
  page.on("request", (request) => { if (request.method() === "GET" && /\/api\/v1\/jobs\/[a-f0-9-]+$/.test(request.url())) stateRequests += 1; });
  await page.getByRole("button", { name: "데모 분석 시작", exact: true }).click();
  await expect(page.getByText("SUCCEEDED", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("progressbar", { name: "Analysis progress" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.getByText("2,000개 결과", { exact: false })).toBeVisible();
  expect(streamAttempts).toBeGreaterThan(0);
  expect(stateRequests).toBeGreaterThan(1);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
});
