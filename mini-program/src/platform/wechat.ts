import { PhoneTransportError, type PhoneTransport } from "../core/phoneClient";
import { type BinaryCodec } from "../core/phoneCrypto";

export const binaryCodec: BinaryCodec = {
  toBase64(bytes) {
    return wx.arrayBufferToBase64(Uint8Array.from(bytes).buffer);
  },
  fromBase64(value) {
    if (
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
        value,
      )
    )
      throw new Error("编码格式无效");
    return new Uint8Array(wx.base64ToArrayBuffer(value));
  },
};

export function secureBytes(length = 32): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    if (typeof wx.getRandomValues !== "function") {
      reject(new Error("当前微信不支持安全配对，请更新微信"));
      return;
    }
    const timer = setTimeout(
      () => reject(new Error("安全随机数生成超时，请重试")),
      10000,
    );
    wx.getRandomValues({
      length,
      success(result) {
        clearTimeout(timer);
        if (result.randomValues.byteLength !== length) {
          reject(new Error("无法建立安全连接"));
          return;
        }
        resolve(new Uint8Array(result.randomValues));
      },
      fail() {
        clearTimeout(timer);
        reject(new Error("无法生成安全连接，请更新微信后重试"));
      },
    });
  });
}

export const phoneTransport: PhoneTransport = (url, envelope) =>
  new Promise((resolve, reject) => {
    wx.request({
      url,
      method: "POST",
      data: envelope,
      timeout: 90000,
      redirect: "manual",
      enableCache: false,
      header: { "Content-Type": "application/json" },
      success(result) {
        if (result.statusCode === 200) {
          resolve(result.data);
          return;
        }
        reject(
          new PhoneTransportError(
            "电脑拒绝连接，请重新配对",
            result.statusCode >= 500,
          ),
        );
      },
      fail() {
        reject(new PhoneTransportError("无法连接电脑，请检查 Wi-Fi"));
      },
    });
  });

export function requireMobileByok(): void {
  const platform = wx.getDeviceInfo().platform;
  const version = wx.getAppBaseInfo().SDKVersion.split(".").map(Number);
  const supported =
    version[0] > 3 ||
    (version[0] === 3 &&
      (version[1] > 2 || (version[1] === 2 && version[2] >= 2)));
  if (!["ios", "android", "devtools"].includes(platform) || !supported) {
    throw new Error(
      "手机 BYOK 需要更新版 iOS/Android 微信（基础库 3.2.2 以上），以保护服务凭据",
    );
  }
}
