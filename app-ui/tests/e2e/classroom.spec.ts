import { expect, test, type Page } from "@playwright/test";

async function startClass(page: Page, name: string) {
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await page.getByRole("button", { name: "新课堂", exact: true }).click();
  await page.getByLabel("课程名称").fill(name);
  await page.getByLabel("记录方式").selectOption("text");
  await page.getByRole("button", { name: "开始记录", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "开始一堂课" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

async function addText(page: Page, text: string) {
  await page.getByLabel("补充课堂文字", { exact: false }).fill(text);
  await page.getByRole("button", { name: "保存课堂文字" }).click();
  await expect(page.locator(".transcript-entry").last()).toContainText(text);
}

test("classroom flow keeps original text through streaming, notes, reload and export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await startClass(page, "数据结构 · 二叉树遍历");
  const original = [
    "今天我们学习二叉树的先序遍历。顺序是先访问根节点，再遍历左子树，最后遍历右子树。",
    "假设根节点是 A，左子节点是 B，右子节点是 C。先序遍历的结果是 A、B、C。注意：访问顺序与节点在纸上的位置不同。",
    "我们可以用递归来表达这个过程。每次进入一个子树，仍然遵循相同的规则；遇到空节点时返回。",
    "接下来把遍历顺序写在笔记里，再尝试手动画一棵树。对比先序、中序和后序遍历，想一想根节点分别在什么时候被访问。",
  ].join("\n\n");
  await addText(page, original);
  await page.getByRole("button", { name: "帮我救场", exact: false }).click();
  await expect(page.locator(".answer-space .markdown")).toContainText("根节点");
  await expect(page.locator(".answer-metrics")).toBeVisible();
  await expect(page.locator(".answer-space .generating")).toHaveCount(0);
  await page.screenshot({ path: "test-results/classroom.png" });
  await page.getByRole("button", { name: "暂停记录" }).click();
  await expect(page.getByRole("button", { name: "继续记录" })).toBeVisible();
  await expect(page.getByLabel("补充课堂文字", { exact: false })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "继续记录" }).click();
  await expect(page.getByLabel("补充课堂文字", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "课堂笔记", exact: false }).click();
  await page.getByRole("button", { name: "整理笔记", exact: true }).click();
  await expect(page.locator(".note-document .markdown")).toContainText(
    "先序遍历",
  );
  await page.screenshot({ path: "test-results/notes.png" });
  await page.getByRole("button", { name: "结束课堂" }).click();
  await expect(
    page.getByRole("button", { name: "开始上课", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".transcript-entry")).toHaveCount(1);
  await expect(page.locator(".transcript-entry")).toContainText(original);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出原文" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("课堂原文.txt");
  const stream = await file.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString("utf8")).toContain(original);
  await page.getByRole("button", { name: "切换紧凑模式" }).click();
  await page.setViewportSize({ width: 430, height: 150 });
  await expect(page.getByRole("button", { name: "展开工作区" })).toBeVisible();
  await page.screenshot({ path: "test-results/compact.png" });
  expect(errors).toEqual([]);
});

test("missing models are actionable and failed startup can recover to text mode", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await page.getByRole("button", { name: "新课堂", exact: true }).click();
  await page.getByLabel("课程名称").fill("离线模型未安装");
  await page.getByRole("button", { name: "开始记录", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "安装离线语音模型",
  );
  await page
    .getByRole("button", { name: "结束未成功启动的课堂，重新选择输入方式" })
    .click();
  await page.getByLabel("记录方式").selectOption("text");
  await page.getByRole("button", { name: "开始记录", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await addText(page, "合成课堂文字");
  await page.getByRole("button", { name: "结束课堂" }).click();
  await expect(
    page.getByRole("button", { name: "开始上课", exact: true }),
  ).toBeVisible();
});

test("settings persist, keywords alert, and unsafe provider errors stay out of answers", async ({
  page,
}) => {
  await startClass(page, "提醒与异常测试");
  await page.getByRole("button", { name: "设置与模型" }).click();
  await page.getByRole("button", { name: "提醒与外观", exact: true }).click();
  await page
    .getByRole("combobox", { name: "主题", exact: true })
    .selectOption("dark");
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/settings-dark.png" });
  await page.getByRole("button", { name: "关闭对话框" }).click();
  await addText(page, "这部分是考试重点，注意先序遍历的顺序。");
  await expect(page.locator(".class-alert")).toContainText("考试");
  await page.getByRole("button", { name: "忽略提醒" }).click();
  await page.route("**/api/v2/sessions/*/assistant", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: "synthetic-unavailable",
        message: "模型服务暂时不可用，请稍后重试",
      }),
    }),
  );
  await page.getByRole("button", { name: "帮我救场", exact: false }).click();
  await expect(page.locator(".error-banner")).toContainText(
    "模型服务暂时不可用",
  );
  await expect(page.locator(".answer-space .markdown")).toHaveCount(0);
  await expect(page.locator(".transcript-entry")).toHaveCount(1);
  await page.getByRole("button", { name: "结束课堂" }).click();
});

test("provider presets save and test a real API path against the isolated synthetic provider", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await page.getByRole("button", { name: "设置与模型" }).click();
  await page.getByRole("button", { name: "问答服务", exact: true }).click();
  await page.getByLabel("运行方式").selectOption("byok");
  await page.getByLabel("服务商预设").selectOption("deepseek");
  await expect(page.getByLabel("兼容 OpenAI 的服务地址")).toHaveValue(
    "https://api.deepseek.com",
  );
  await expect(page.getByLabel("模型名称", { exact: true })).toHaveValue(
    "deepseek-flash",
  );
  await page.getByRole("button", { name: "保存配置并测试连接" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "连接成功 · 首字" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭对话框" }).click();
});

test("imports a real document, associates it with a classroom and cancels generation without losing text", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await page.getByRole("button", { name: "课程资料", exact: false }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "进程隔离讲义.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# 进程隔离\n课程资料用于讲解地址空间与资源隔离。",
      "utf8",
    ),
  });
  await expect(
    page.getByRole("heading", { name: "进程隔离讲义.md" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新课堂", exact: true }).click();
  await page.getByLabel("课程名称").fill("资料与取消");
  await page.getByLabel("记录方式").selectOption("text");
  await page
    .getByLabel("本堂课的参考资料")
    .selectOption({ label: "进程隔离讲义.md" });
  await page.getByRole("button", { name: "开始记录", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await addText(page, "进程拥有独立的虚拟地址空间；这段原文需要保留。");
  await page.getByLabel("向课堂助手追问").fill("举例解释地址空间隔离");
  await page.getByRole("button", { name: "发送追问" }).click();
  await expect(page.locator(".answer-space .markdown")).toBeVisible();
  await page
    .locator(".answer-space")
    .getByRole("button", { name: "停止", exact: true })
    .click();
  await expect(page.locator(".answer-space .generating")).toHaveCount(0);
  await expect(page.locator(".transcript-entry")).toContainText(
    "这段原文需要保留",
  );
  await page.getByRole("button", { name: "结束课堂" }).click();
});
