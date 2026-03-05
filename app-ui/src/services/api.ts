/**
 * API 服务模块
 * ============
 * 封装所有与 FastAPI 后端的 HTTP 通信
 */

// 后端地址（开发环境）
const API_BASE = "http://127.0.0.1:8765/api";

/**
 * 上传 PPT 文件到后端进行解析
 */
export async function uploadPPT(file: File): Promise<{
  status: string;
  message: string;
  text_length: number;
}> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload_ppt`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "上传失败");
  }
  return res.json();
}

/**
 * 启动摸鱼监控模式
 */
export async function startMonitor(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/start_monitor`, { method: "POST" });
  if (!res.ok) throw new Error("启动监控失败");
  return res.json();
}

/**
 * 停止监控
 */
export async function stopMonitor(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/stop_monitor`, { method: "POST" });
  if (!res.ok) throw new Error("停止监控失败");
  return res.json();
}

/**
 * 紧急救场 - 获取课堂上下文、问题和答案
 */
export async function emergencyRescue(): Promise<{
  status: string;
  context: string;
  question: string;
  answer: string;
}> {
  const res = await fetch(`${API_BASE}/emergency_rescue`, { method: "POST" });
  if (!res.ok) throw new Error("救场请求失败");
  return res.json();
}

/**
 * 生成课后总结
 */
export async function generateSummary(): Promise<{
  status: string;
  filename: string;
  summary: string;
}> {
  const res = await fetch(`${API_BASE}/generate_summary`, { method: "POST" });
  if (!res.ok) throw new Error("生成总结失败");
  return res.json();
}

/**
 * 更新自定义关键词
 */
export async function updateKeywords(keywords: string[]): Promise<{
  status: string;
  all_keywords: string[];
}> {
  const res = await fetch(`${API_BASE}/update_keywords`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keywords }),
  });
  if (!res.ok) throw new Error("更新关键词失败");
  return res.json();
}

/**
 * 获取当前关键词列表
 */
export async function getKeywords(): Promise<{
  builtin: string[];
  custom: string[];
  all: string[];
}> {
  const res = await fetch(`${API_BASE}/keywords`);
  if (!res.ok) throw new Error("获取关键词失败");
  return res.json();
}
