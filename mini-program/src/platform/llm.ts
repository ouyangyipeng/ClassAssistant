import { CompletionStream } from "../core/sse";
import {
  llmPresets,
  providerMessage,
  type LlmProvider,
} from "../core/providers";
import { utf8 } from "../core/phoneCrypto";
import { requireMobileByok } from "./wechat";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
export interface Generation {
  done: Promise<string>;
  cancel(): void;
}
export class GenerationCancelled extends Error {
  constructor() {
    super("已取消生成，原文仍已保留");
  }
}

export function generate(
  provider: LlmProvider,
  model: string,
  key: string,
  messages: ChatMessage[],
  emit: (text: string) => void,
): Generation {
  requireMobileByok();
  if (!key.trim() || key.length > 4096 || /[\r\n]/.test(key))
    throw new Error("请先填写有效的问答 API Key");
  if (!model.trim() || model.length > 200)
    throw new Error("请填写有效的模型名称");
  const preset = llmPresets[provider];
  if (!Object.hasOwn(llmPresets, provider))
    throw new Error("请选择受支持的问答服务");
  let task: WechatMiniprogram.RequestTask | undefined;
  let finish: (error?: Error) => void = () => undefined;
  const done = new Promise<string>((resolve, reject) => {
    let settled = false,
      received = false,
      output = "";
    const stream = new CompletionStream((text) => {
      output += text;
      emit(text);
    });
    const timer = setTimeout(() => {
      finish(new Error("模型响应超时，请重试或更换模型"));
      task?.abort();
    }, 60000);
    finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(output);
    };
    const consume = (bytes: Uint8Array) => {
      if (settled) return;
      try {
        stream.feed(bytes);
      } catch {
        finish(new Error("回答不完整或格式无效；原文仍已保留，可重试生成"));
        task?.abort();
      }
    };
    try {
      task = wx.request<ArrayBuffer>({
        url: preset.url,
        method: "POST",
        timeout: 60000,
        enableChunked: true,
        responseType: "arraybuffer",
        dataType: "text",
        redirect: "manual",
        enableCache: false,
        header: {
          Authorization: `Bearer ${key.trim()}`,
          "Content-Type": "application/json",
        },
        data: {
          model: model.trim(),
          messages,
          stream: true,
          max_tokens: 2048,
          ...preset.parameters,
        },
        success(result) {
          if (settled) return;
          if (result.statusCode !== 200) {
            finish(new Error(providerMessage(result.statusCode)));
            return;
          }
          if (!received)
            consume(
              typeof result.data === "string"
                ? utf8(result.data)
                : new Uint8Array(result.data),
            );
          if (settled) return;
          try {
            stream.finish();
            finish();
          } catch {
            finish(
              new Error("模型连接提前结束，已显示的部分内容未保存为完整笔记"),
            );
          }
        },
        fail() {
          finish(new Error("模型连接失败，请检查网络、域名配置和服务凭据"));
        },
      });
      task.onHeadersReceived((result) => {
        if (result.statusCode && result.statusCode !== 200) {
          finish(new Error(providerMessage(result.statusCode)));
          task?.abort();
        }
      });
      task.onChunkReceived((result) => {
        received = true;
        consume(new Uint8Array(result.data));
      });
    } catch {
      finish(new Error("当前微信无法发送模型请求，请更新微信后重试"));
    }
  });
  return {
    done,
    cancel() {
      finish(new GenerationCancelled());
      task?.abort();
    },
  };
}
