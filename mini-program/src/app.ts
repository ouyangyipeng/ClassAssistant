import { service, privacyGate } from "./runtime";

App({
  onLaunch() {
    privacyGate();
    service();
  },
  onShow() {
    service().foregrounded();
  },
  onHide() {
    privacyGate().finish(false);
    service().background();
  },
});
