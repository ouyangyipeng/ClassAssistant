export const llmPresets = {
  dashscope: {
    label: "阿里云百炼 · 北京",
    url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    model: "qwen-plus",
    parameters: { enable_thinking: false },
  },
  dashscopeIntl: {
    label: "阿里云百炼 · 新加坡",
    url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    model: "qwen-plus",
    parameters: { enable_thinking: false },
  },
  deepseek: {
    label: "DeepSeek",
    url: "https://api.deepseek.com/chat/completions",
    model: "deepseek-flash",
    parameters: { thinking: { type: "disabled" } },
  },
} as const;
export type LlmProvider = keyof typeof llmPresets;
export const speechPresets = {
  beijing: {
    label: "阿里云百炼 · 北京",
    url: "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
  },
  singapore: {
    label: "阿里云百炼 · 新加坡",
    url: "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
  },
} as const;
export type SpeechRegion = keyof typeof speechPresets;

export interface MobileSettings {
  mode: "byok" | "desktop";
  llmProvider: LlmProvider;
  model: string;
  speechRegion: SpeechRegion;
  speechModel: string;
  keywords: string[];
}
export const defaultSettings: MobileSettings = {
  mode: "byok",
  llmProvider: "dashscope",
  model: "qwen-plus",
  speechRegion: "beijing",
  speechModel: "fun-asr-realtime",
  keywords: ["提问", "考试", "重点", "作业"],
};

// Keys are intentionally absent from MobileSettings and every storage record.
export interface MemoryCredentials {
  llm: string;
  speech: string;
}

export function providerMessage(status: number): string {
  if (status === 401 || status === 403)
    return "服务凭据无效，请检查 API Key 与所选地区";
  if (status === 429) return "服务额度不足或请求频繁，请检查余额后重试";
  if (status >= 300 && status < 400)
    return "服务要求跳转，已停止发送以保护凭据；请更新小程序";
  return "服务暂时不可用，请检查所选模型与网络后重试";
}
