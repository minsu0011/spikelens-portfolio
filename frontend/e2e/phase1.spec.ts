import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

test("Phase 1: actual PostgreSQL events render through FastAPI and Next.js", async ({ page }) => {
  const evidence = path.resolve("../docs/evidence");
  await mkdir(evidence, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 980 });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Make every event visible." })).toBeVisible();
  await expect(page.getByText("SYNTHETIC DEMO", { exact: true })).toBeVisible();
  await expect(page.locator(".preview-value")).not.toContainText("—");
  await page.screenshot({ path: path.join(evidence, "ui-landing.png"), fullPage: true });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  const apiResponse = await page.request.get("/api/v1/events?limit=15&page=1");
  expect(apiResponse.ok()).toBe(true);
  const data = await apiResponse.json();
  expect(data.total).toBeGreaterThanOrEqual(10_000);
  expect(data.items[0].is_synthetic).toBe(true);
  await page.screenshot({ path: path.join(evidence, "ui-overview.png"), fullPage: true });

  await page.goto("/events");
  await expect(page.locator("tbody tr")).toHaveCount(15);
  await page.screenshot({ path: path.join(evidence, "ui-events.png"), fullPage: true });
  await page.locator("tbody .symbol-link").first().click();
  await expect(page.getByRole("heading", { name: "Observed price path" })).toBeVisible();
  await expect(page.getByText("SYNTHETIC EVENT", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(evidence, "ui-event-detail.png"), fullPage: true });
  expect(errors).toEqual([]);
});
