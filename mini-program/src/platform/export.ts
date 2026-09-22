import { exportClassroom, type ClassroomRecord } from "../core/records";

export async function exportFile(record: ClassroomRecord): Promise<void> {
  const path = `${wx.env.USER_DATA_PATH}/classfox-${record.id}.md`,
    fs = wx.getFileSystemManager();
  await new Promise<void>((resolve, reject) =>
    fs.writeFile({
      filePath: path,
      data: exportClassroom(record),
      encoding: "utf8",
      success: () => resolve(),
      fail: () =>
        reject(new Error("导出文件写入失败，请复制课堂原文后清理空间")),
    }),
  );
  try {
    await new Promise<void>((resolve, reject) =>
      wx.shareFileMessage({
        filePath: path,
        fileName: `课狐-${record.courseName.replace(/[\\/:*?"<>|\r\n]/g, "_").slice(0, 60)}.md`,
        success: () => resolve(),
        fail: () =>
          reject(
            new Error("文件分享未完成，课堂仍保存在本机，也可选择复制全文"),
          ),
      }),
    );
  } finally {
    // Only remove the export created here, after the user's share operation settles.
    await new Promise<void>((resolve, reject) =>
      fs.unlink({
        filePath: path,
        success: () => resolve(),
        fail: () =>
          reject(new Error("导出临时文件未能清理，请在微信中清理小程序文件")),
      }),
    );
  }
}
