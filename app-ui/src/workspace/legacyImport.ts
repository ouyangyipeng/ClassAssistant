export interface LegacyImportResult {
  session_id: string | null;
  materials: number;
  notes: number;
  skipped_files: string[];
}

export function describeImport(result: LegacyImportResult): string {
  const count = Number(Boolean(result.session_id)) + result.materials + result.notes;
  const summary = count
    ? `已处理课堂 ${Number(Boolean(result.session_id))} 堂、资料 ${result.materials} 份、笔记 ${result.notes} 份。重复导入会复用已有记录。`
    : "未导入任何记录。请确认选择的是旧版 data 目录，且包含非空课堂、资料或笔记文件。";
  return result.skipped_files.length
    ? `${summary} 以下文件因格式、编码或大小限制未导入，原文件仍保留：${result.skipped_files.join("、")}`
    : summary;
}
