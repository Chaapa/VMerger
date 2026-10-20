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
  await page.getByLabel("Ключ пространства").fill(token);
  await page.getByRole("button", { name: "Открыть пространство" }).click();
  await expect(
    page.getByRole("heading", { name: "Ваши истории" }),
  ).toBeVisible();
  mkdirSync(resolve(root, "docs/images"), { recursive: true });
  await page.screenshot({
    path: resolve(root, "docs/images/workspace.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Новый проект", exact: true })
    .last()
    .click();
  await page.getByLabel("Название проекта").fill("Локальная проверка");
  await page
    .getByLabel("О чём ваши видео?")
    .fill("Проверка интерфейса. Здесь нет демонстрационных AI-результатов.");
  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/projects") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Создать проект" }).click();
  const project = await (await created).json();
  mkdirSync(resolve(root, ".local"), { recursive: true });
  writeFileSync(
    resolve(root, ".local/browser-project.json"),
    JSON.stringify({ id: project.id }),
  );
  await expect(
    page.getByRole("heading", { name: "Локальная проверка" }),
  ).toBeVisible();
  await expect(page.getByLabel("Пожелание к видео")).toBeDisabled();
  await page.screenshot({
    path: resolve(root, "docs/images/project.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Качество и работа агентов" }).click();
  await expect(page.getByText("Вызовов ещё не было.")).toBeVisible();
  await expect(page.getByText("0 наблюдений")).toBeVisible();
  await page.screenshot({
    path: resolve(root, "docs/images/metrics.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Сменить тему" }).click();
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
    .getByRole("button", { name: "Истории", exact: false })
    .first()
    .click();
  await expect(page.getByLabel("Пожелание к видео")).toBeVisible();
  expect(errors).toEqual([]);
});
