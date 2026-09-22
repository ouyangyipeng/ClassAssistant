import { service } from "../../service";
import {
  llmPresets,
  speechPresets,
  type LlmProvider,
  type SpeechRegion,
  type MobileSettings,
} from "../../core/providers";

const providers = Object.keys(llmPresets) as LlmProvider[],
  regions = Object.keys(speechPresets) as SpeechRegion[];
export function registerSettings(): void {
  Page({
    data: {
      mode: "byok",
      providerNames: providers.map((id) => llmPresets[id].label),
      regionNames: regions.map((id) => speechPresets[id].label),
      providerIndex: 0,
      regionIndex: 0,
      model: "",
      speechModel: "",
      llmKey: "",
      speechKey: "",
      keywords: "",
      hasLlm: false,
      hasSpeech: false,
      paired: false,
      pairingCode: "",
      error: "",
      saved: false,
      busy: false,
    },
    unsubscribe: null as (() => void) | null,
    onShow() {
      const app = service(),
        value = app.snapshot.settings,
        keys = app.credentialStatus();
      this.setData({
        mode: value.mode,
        providerIndex: providers.indexOf(value.llmProvider),
        regionIndex: regions.indexOf(value.speechRegion),
        model: value.model,
        speechModel: value.speechModel,
        keywords: value.keywords.join("，"),
        hasLlm: keys.llm,
        hasSpeech: keys.speech,
      });
      this.unsubscribe?.();
      this.unsubscribe = app.subscribe((state) =>
        this.setData({
          paired: state.paired,
          pairingCode: state.pairingCode,
          error: state.error,
        }),
      );
    },
    onHide() {
      this.unsubscribe?.();
      this.unsubscribe = null;
      this.setData({ llmKey: "", speechKey: "" });
    },
    onUnload() {
      this.unsubscribe?.();
    },
    setMode(event: WechatMiniprogram.TouchEvent) {
      this.setData({
        mode:
          event.currentTarget.dataset.mode === "desktop" ? "desktop" : "byok",
        saved: false,
      });
    },
    provider(event: WechatMiniprogram.PickerChange) {
      const index = Number(event.detail.value);
      if (providers[index])
        this.setData({
          providerIndex: index,
          model: llmPresets[providers[index]].model,
          llmKey: "",
          saved: false,
        });
    },
    region(event: WechatMiniprogram.PickerChange) {
      const index = Number(event.detail.value);
      if (regions[index])
        this.setData({ regionIndex: index, speechKey: "", saved: false });
    },
    input(event: WechatMiniprogram.Input) {
      const field = event.currentTarget.dataset.field as string;
      if (
        !["model", "speechModel", "llmKey", "speechKey", "keywords"].includes(
          field,
        )
      )
        return;
      this.setData({ [field]: event.detail.value, saved: false });
    },
    save() {
      try {
        const settings: MobileSettings = {
          mode: this.data.mode === "desktop" ? "desktop" : "byok",
          llmProvider: providers[this.data.providerIndex],
          speechRegion: regions[this.data.regionIndex],
          model: this.data.model.trim(),
          speechModel: this.data.speechModel.trim(),
          keywords: [
            ...new Set(
              this.data.keywords
                .split(/[,，\n]/)
                .map((value) => value.trim())
                .filter(Boolean),
            ),
          ],
        };
        service().configure(settings, {
          llm: this.data.llmKey,
          speech: this.data.speechKey,
        });
        const status = service().credentialStatus();
        this.setData({
          llmKey: "",
          speechKey: "",
          saved: true,
          hasLlm: status.llm,
          hasSpeech: status.speech,
        });
      } catch (error) {
        service().report(error);
      }
    },
    forget() {
      try {
        service().clearCredentials();
        this.setData({
          hasLlm: false,
          hasSpeech: false,
          llmKey: "",
          speechKey: "",
          saved: false,
        });
      } catch (error) {
        service().report(error);
      }
    },
    scan() {
      if (this.data.busy) return;
      this.setData({ busy: true });
      wx.scanCode({
        onlyFromCamera: true,
        scanType: ["qrCode"],
        success: (result) => {
          void service()
            .pair(result.result)
            .catch((error: unknown) => service().report(error))
            .finally(() => this.setData({ busy: false }));
        },
        fail: () => {
          this.setData({ busy: false });
          service().report(new Error("扫码未完成，请重新扫描电脑上的二维码"));
        },
      });
    },
    async confirm() {
      if (this.data.busy) return;
      this.setData({ busy: true });
      try {
        await service().confirmPair();
      } catch (error) {
        service().report(error);
      } finally {
        this.setData({ busy: false });
      }
    },
    permissions() {
      wx.openSetting({
        fail: () =>
          service().report(
            new Error("无法打开权限设置，请从微信小程序菜单进入"),
          ),
      });
    },
    privacy() {
      wx.showModal({
        title: "课堂数据如何使用",
        showCancel: false,
        confirmText: "我知道了",
        content:
          "只有点击录音才会采集麦克风，离开课堂会暂停。BYOK 将音频直接发送至你选择的阿里云百炼地区，将课堂文字发送至所选问答服务；服务商可能依其条款保存数据。电脑模式通过配对加密通道使用电脑本地模型。原文和笔记保存在本机；导出分享由你操作。Key 和配对密钥仅留在本次小程序内存，重新打开需填写或配对。微信录音临时文件在停止后清理。删除小程序可能清除记录，请及时导出。请事先取得参与者录音许可。",
      });
    },
  });
}
