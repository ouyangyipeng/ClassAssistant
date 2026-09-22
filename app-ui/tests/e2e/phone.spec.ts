import { expect, test } from "@playwright/test";

test("phone pairing stays opt-in, hides consumed QR, and binds approval to this device", async ({
  page,
}) => {
  type Connection = {
    id: string;
    name: string;
    state: string;
    client_nonce: string;
    verification_code: string | null;
    expires_in: number;
  };
  let listening = false;
  let connections: Connection[] = [];
  const id = "a".repeat(32),
    nonce = "b".repeat(64);
  let approvedNonce = "";
  await page.route("**/api/v2/phone**", async (route) => {
    const url = new URL(route.request().url()),
      method = route.request().method();
    let body: object;
    if (url.pathname.endsWith("/addresses"))
      body = { addresses: ["192.168.1.20"], message: "" };
    else if (url.pathname.endsWith("/offers")) {
      connections = [
        {
          id,
          name: "",
          state: "offered",
          client_nonce: "",
          verification_code: null,
          expires_in: 120,
        },
      ];
      body = {
        version: 1,
        id,
        secret: "01".repeat(32),
        address: "192.168.1.20",
        port: 40001,
        expires_in: 120,
      };
    } else if (url.pathname.endsWith("/approve")) {
      approvedNonce = (
        route.request().postDataJSON() as { client_nonce: string }
      ).client_nonce;
      connections[0].state = "approved";
      body = { approved: true };
    } else {
      if (method === "POST") listening = true;
      if (method === "DELETE") {
        listening = false;
        connections = [];
      }
      body = {
        listening,
        address: listening ? "192.168.1.20" : null,
        port: listening ? 40001 : null,
        connections,
      };
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await page.getByRole("button", { name: "设置与模型" }).click();
  await page
    .getByRole("button", { name: "微信预览 · v2.5", exact: true })
    .click();
  await expect(page.getByLabel("此电脑的 Wi-Fi IPv4 地址")).toHaveValue(
    "192.168.1.20",
  );
  expect(listening).toBe(false);
  await page.getByRole("button", { name: "开启手机连接", exact: true }).click();
  await page
    .getByRole("button", { name: "生成配对二维码", exact: true })
    .click();
  await expect(page.locator(".phone-qr svg")).toBeVisible();
  await page.screenshot({ path: "test-results/phone-pairing.png" });
  connections = [
    {
      id,
      name: "合成手机",
      state: "pending",
      client_nonce: nonce,
      verification_code: "123456",
      expires_in: 100,
    },
  ];
  await expect(page.getByLabel("配对核对数字")).toHaveText("123456");
  await expect(page.locator(".phone-qr")).toHaveCount(0);
  await page.getByRole("button", { name: "数字一致，允许连接" }).click();
  expect(approvedNonce).toBe(nonce);
  await page.getByRole("button", { name: "关闭所有手机连接" }).click();
  await expect(
    page.getByRole("button", { name: "开启手机连接", exact: true }),
  ).toBeVisible();
  expect(listening).toBe(false);
});
