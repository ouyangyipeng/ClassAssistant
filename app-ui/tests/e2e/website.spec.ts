import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18866" });

test("product page previews follow keyboard selection and retain download links", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "留在课堂",
  );
  const notes = page.getByRole("tab", { name: "课后笔记" });
  await notes.click();
  await expect(page.getByRole("tabpanel").getByRole("img")).toHaveAttribute(
    "src",
    "assets/notes.png",
  );
  await notes.press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "课堂与问答" })).toBeFocused();
  await expect(page.getByRole("tabpanel").getByRole("img")).toHaveAttribute(
    "src",
    "assets/classroom.png",
  );
  await expect(page.locator(".download-card")).toHaveCount(3);
  for (const link of await page.locator(".download-card").all()) {
    await expect(link).toHaveAttribute(
      "href",
      /^https:\/\/github\.com\/ouyangyipeng\/ClassAssistant\/releases\/download\/v2\.0\.1\/ClassFox_2\.0\.1_/,
    );
  }
  await page.getByRole("link", { name: "ClassFox 首页", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Array.from(document.images)
          .filter((image) => image.loading !== "lazy")
          .every((image) => image.complete && image.naturalWidth > 0),
      ),
    )
    .toBe(true);
  await page.screenshot({ path: "test-results/website-desktop.png" });
});

test("mobile page fits narrow screens and discloses WeChat preview status", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "下载课狐", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.getByText("可以直接在微信里使用吗？", { exact: true }).click();
  await expect(page.locator("details[open]")).toContainText("v2.5 正式交付");
  await page.getByRole("link", { name: "ClassFox 首页", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Array.from(document.images)
          .filter((image) => image.loading !== "lazy")
          .every((image) => image.complete && image.naturalWidth > 0),
      ),
    )
    .toBe(true);
  await page.screenshot({ path: "test-results/website-mobile.png" });
});

test.describe("static and reduced-motion fallback", () => {
  test.use({ javaScriptEnabled: false, reducedMotion: "reduce" });

  test("core content, FAQ and downloads work without JavaScript", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("tablist")).toBeHidden();
    await page.getByText("课狐免费吗？", { exact: true }).click();
    await expect(page.locator("details[open]")).toContainText("MIT");
    await expect(page.locator(".download-card")).toHaveCount(3);
    expect(
      await page.evaluate(
        () => getComputedStyle(document.documentElement).scrollBehavior,
      ),
    ).toBe("auto");
  });
});
