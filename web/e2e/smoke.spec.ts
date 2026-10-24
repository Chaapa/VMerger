import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve("..");
const token =
  process.env.APP_TOKEN ||
  readFileSync(resolve(root, ".env"), "utf8")
    .split("\n")
    .find((l) => l.startsWith("APP_TOKEN="))!
    .slice(10)
    .trim();

test("real workspace, empty metrics, dark theme and mobile layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByLabel("Workspace key").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your stories" }),
  ).toBeVisible();
  mkdirSync(resolve(root, "docs/images"), { recursive: true });
  await page.screenshot({
    path: resolve(root, "docs/images/workspace.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "New project", exact: true })
    .last()
    .click();
  await page.getByLabel("Project title").fill("Local validation");
  await page
    .getByLabel("What is your footage about?")
    .fill("Interface validation. No demonstration AI results are shown.");
  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/projects") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create project" }).click();
  const project = await (await created).json();
  mkdirSync(resolve(root, ".local"), { recursive: true });
  writeFileSync(
    resolve(root, ".local/browser-project.json"),
    JSON.stringify({ id: project.id }),
  );
  await expect(
    page.getByRole("heading", { name: "Local validation", level: 1 }),
  ).toBeVisible();
  await expect(page.getByLabel("Video request")).toBeDisabled();
  await page.screenshot({
    path: resolve(root, "docs/images/project.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Sources/ }).click();
  await expect(
    page.getByRole("button", { name: "Analyze", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Rebuild search", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Quality and agents" }).click();
  await expect(page.getByRole("heading", { name: "AI team" })).toBeVisible();
  await expect(page.getByText("Video analyst", { exact: true })).toBeVisible();
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible();
  await expect(page.getByText("No calls yet.")).toBeVisible();
  await expect(page.getByText("0 observations")).toBeVisible();
  await page.screenshot({
    path: resolve(root, "docs/images/metrics.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: resolve(root, ".local/mobile.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Stories", exact: false })
    .first()
    .click();
  await expect(page.getByLabel("Video request")).toBeVisible();
  expect(errors).toEqual([]);
});
