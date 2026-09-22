import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";

const dist = new URL("../dist/", import.meta.url);
test("built WXML conditional directives evaluate data expressions", async () => {
  for (const file of ["components/privacy/index.wxml", "pages/classroom/index.wxml", "pages/history/index.wxml", "pages/settings/index.wxml"]) {
    const template = await readFile(new URL(file, dist), "utf8");
    for (const match of template.matchAll(/wx:(?:if|elif)="([^"]+)"/g)) {
      assert.match(match[1], /^\{\{[\s\S]+\}\}$/, `${file}: conditional must bind to page data`);
    }
  }
});
test("the built native pages share one runtime and persist a text classroom across navigation", async () => {
  const stored = new Map();
  let recorderOwners = 0,
    serial = 0,
    registeredPage,
    app;
  const wx = {
    getStorageSync: (key) => stored.get(key),
    setStorageSync: (key, value) => stored.set(key, structuredClone(value)),
    getStorageInfoSync: () => ({ keys: [...stored.keys()] }),
    removeStorageSync: (key) => stored.delete(key),
    getRecorderManager() {
      recorderOwners++;
      return {
        onStart() {},
        onStop() {},
        onError() {},
        onInterruptionBegin() {},
        onFrameRecorded() {},
      };
    },
    getRandomValues: (options) =>
      options.success({
        randomValues: new Uint8Array(options.length).fill(++serial).buffer,
      }),
    vibrateShort() {},
    switchTab() {},
  };
  const context = vm.createContext({
    wx,
    Uint8Array,
    ArrayBuffer,
    DataView,
    TextDecoder,
    TextEncoder,
    setTimeout,
    clearTimeout,
    App: (value) => {
      app = value;
    },
    Page: (value) => {
      registeredPage = value;
    },
  });
  const module = { exports: {} };
  context.module = module;
  vm.runInContext(await readFile(new URL("runtime.js", dist), "utf8"), context);
  const runtime = module.exports;
  context.require = (name) => {
    assert.ok(["./runtime", "../../runtime.js"].includes(name));
    return runtime;
  };
  vm.runInContext(await readFile(new URL("app.js", dist), "utf8"), context);
  app.onLaunch();
  app.onShow();
  function instance() {
    const page = registeredPage;
    page.data = structuredClone(page.data);
    page.setData = (update) => Object.assign(page.data, update);
    return page;
  }
  vm.runInContext(
    await readFile(new URL("pages/classroom/index.js", dist), "utf8"),
    context,
  );
  const classroom = instance();
  classroom.onShow();
  classroom.data.title = "构建后课堂";
  await classroom.run(() => runtime.service().create(classroom.data.title));
  await classroom.run(() => runtime.service().append("正文重点 🦊"));
  assert.equal(classroom.data.entries[0].text, "正文重点 🦊");
  await classroom.run(() => runtime.service().finishClass());
  classroom.onHide();
  vm.runInContext(
    await readFile(new URL("pages/history/index.js", dist), "utf8"),
    context,
  );
  const history = instance();
  history.onShow();
  assert.equal(history.data.records.length, 1);
  assert.equal(history.data.records[0].name, "构建后课堂");
  vm.runInContext(
    await readFile(new URL("pages/settings/index.js", dist), "utf8"),
    context,
  );
  const settings = instance();
  settings.onShow();
  settings.onHide();
  assert.equal(recorderOwners, 1);
  assert.equal(runtime.service().snapshot.record.entries.length, 1);
  app.onHide();
});
