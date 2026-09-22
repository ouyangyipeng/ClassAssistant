import { service, message } from "../../service";
import { exportFile } from "../../platform/export";

export function registerHistory(): void {
  Page({
    data: {
      records: [] as Array<{
        id: string;
        name: string;
        date: string;
        count: number;
        notes: number;
        mode: string;
      }>,
      error: "",
      busy: false,
    },
    onShow() {
      this.refresh();
    },
    refresh() {
      try {
        const history = service().repository.inspect();
        this.setData({
          records: history.records.map((record) => ({
            id: record.id,
            name: record.courseName,
            date: new Date(record.createdAt).toLocaleString("zh-CN", {
              hour12: false,
            }),
            count: record.entries.length,
            notes: record.notes.length,
            mode: record.mode === "byok" ? "手机 BYOK" : "电脑本地模型",
          })),
          error: history.damaged.length
            ? `有 ${history.damaged.length} 堂课的数据格式异常，原始存储仍保留。请勿清除小程序数据；下方正常课堂仍可查看与导出。`
            : "",
        });
      } catch (error) {
        this.setData({ error: message(error) });
      }
    },
    open(event: WechatMiniprogram.TouchEvent) {
      try {
        service().load(String(event.currentTarget.dataset.id));
        wx.switchTab({ url: "/pages/classroom/index" });
      } catch (error) {
        this.setData({ error: message(error) });
      }
    },
    async export(event: WechatMiniprogram.TouchEvent) {
      if (this.data.busy) return;
      this.setData({ busy: true });
      try {
        await exportFile(
          service().repository.load(String(event.currentTarget.dataset.id)),
        );
      } catch (error) {
        this.setData({ error: message(error) });
      } finally {
        this.setData({ busy: false });
      }
    },
    remove(event: WechatMiniprogram.TouchEvent) {
      const id = String(event.currentTarget.dataset.id);
      if (service().snapshot.record?.id === id) {
        this.setData({ error: "请先切换或新建课堂，再删除当前打开的记录" });
        return;
      }
      wx.showModal({
        title: "删除本机课堂？",
        content: "此操作不可撤销。请先导出原文与笔记。电脑副本不受影响。",
        confirmText: "删除",
        confirmColor: "#a53f36",
        success: (result) => {
          if (!result.confirm) return;
          try {
            service().repository.remove(id);
            this.refresh();
          } catch {
            this.setData({ error: "删除失败，原记录仍保留，请重试" });
          }
        },
      });
    },
  });
}
