import { privacyGate } from "../../platform/privacy";

const subscriptions = new WeakMap<object, () => void>();
export function registerPrivacy(): void {
  Component({
    data: { visible: false },
    lifetimes: {
      attached() {
        subscriptions.set(
          this,
          privacyGate().subscribe((visible) => this.setData({ visible })),
        );
      },
      detached() {
        subscriptions.get(this)?.();
        subscriptions.delete(this);
      },
    },
    pageLifetimes: {
      hide() {
        privacyGate().finish(false);
      },
    },
    methods: {
      agree() {
        privacyGate().finish(true);
      },
      disagree() {
        privacyGate().finish(false);
      },
      contract() {
        wx.openPrivacyContract({
          fail: () => wx.showToast({ title: "隐私指引尚未配置", icon: "none" }),
        });
      },
      blockTouch() {},
    },
  });
}
