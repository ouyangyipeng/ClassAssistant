// One bundled module owns all app state and the sole native RecorderManager.
export { service } from "./service";
export { registerClassroom } from "./pages/classroom/index";
export { registerSettings } from "./pages/settings/index";
export { registerHistory } from "./pages/history/index";
export { registerPrivacy } from "./components/privacy/index";
export { privacyGate } from "./platform/privacy";
