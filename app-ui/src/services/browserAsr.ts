import { ingestAsrText } from "./api";

type SpeechRecognitionResultLike = {
    isFinal: boolean;
    [index: number]: { transcript?: string };
};

type SpeechRecognitionEventLike = {
    resultIndex: number;
    results: Array<SpeechRecognitionResultLike>;
};

type RecognitionConstructor = new () => {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    maxAlternatives: number;
    start: () => void;
    stop: () => void;
    abort: () => void;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    onerror: ((event: { error?: string; message?: string }) => void) | null;
    onend: (() => void) | null;
};

export interface BrowserAsrSession {
    start: () => Promise<void>;
    stop: () => Promise<void>;
}

export interface BrowserAsrOptions {
    lang?: string;
    sessionToken: string;
}

const AUTO_RESTART_DELAY_MS = 400;
const DEDUPE_WINDOW_MS = 2000;

function getErrorName(error: unknown): string {
    if (typeof error === "object" && error !== null && "name" in error) {
        const value = (error as { name?: unknown }).name;
        if (typeof value === "string") {
            return value;
        }
    }
    return "UnknownError";
}

function getErrorMessage(error: unknown): string {
    if (error instanceof Error && error.message) {
        return error.message;
    }
    if (typeof error === "string") {
        return error;
    }
    return "未知错误";
}

function isRetryableStartError(error: unknown): boolean {
    // InvalidStateError 常见于短时间内重复 start，通常可短暂重试。
    return getErrorName(error) === "InvalidStateError";
}

function getRecognitionConstructor(): RecognitionConstructor | null {
    const globalWindow = window as Window & {
        SpeechRecognition?: RecognitionConstructor;
        webkitSpeechRecognition?: RecognitionConstructor;
    };

    return (
        globalWindow.SpeechRecognition ||
        globalWindow.webkitSpeechRecognition ||
        null
    );
}

export function createBrowserAsrSession(
    options: BrowserAsrOptions,
    onStatus?: (message: string) => void,
): BrowserAsrSession {
    const opts = options;
    const Recognition = getRecognitionConstructor();
    if (!Recognition) {
        throw new Error(
            "当前浏览器/内核不支持 SpeechRecognition / webkitSpeechRecognition",
        );
    }

    const sessionToken = opts.sessionToken?.trim();
    if (!sessionToken) {
        throw new Error("浏览器语音会话令牌缺失，无法注入识别结果");
    }

    const recognition = new Recognition();
    recognition.lang = opts.lang?.trim() || "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    let isRunning = false;
    let isManuallyStopped = false;
    let restartTimer: number | null = null;
    let lastSentFinalTranscript = "";
    let lastSentFinalAt = 0;
    let sendQueue: Promise<void> = Promise.resolve();

    const clearRestartTimer = () => {
        if (restartTimer !== null) {
            window.clearTimeout(restartTimer);
            restartTimer = null;
        }
    };

    const sendTranscript = (transcript: string) => {
        const now = Date.now();
        if (
            transcript === lastSentFinalTranscript &&
            now - lastSentFinalAt < DEDUPE_WINDOW_MS
        ) {
            return;
        }

        sendQueue = sendQueue
            .then(() => {
                if (!isRunning || isManuallyStopped) {
                    return;
                }

                return ingestAsrText({
                    text: transcript,
                    is_final: true,
                    asr_session_token: sessionToken,
                });
            })
            .then(() => {
                // 仅在后端确认接收成功后更新去重状态，避免失败后同文本被窗口抑制。
                lastSentFinalTranscript = transcript;
                lastSentFinalAt = Date.now();
            })
            .catch((error) => {
                // Avoid reporting errors after the session has been stopped.
                if (!isRunning || isManuallyStopped) {
                    return;
                }
                onStatus?.(
                    error instanceof Error ? error.message : "浏览器语音文本注入失败",
                );
            });
    };

    const scheduleRestart = () => {
        clearRestartTimer();
        restartTimer = window.setTimeout(() => {
            restartTimer = null;
            if (!isRunning || isManuallyStopped) {
                return;
            }

            try {
                recognition.start();
            } catch (error) {
                const retryable = isRetryableStartError(error);
                onStatus?.(
                    retryable
                        ? `浏览器语音重启中：${getErrorName(error)} - ${getErrorMessage(error)}`
                        : `浏览器语音重启失败：${getErrorName(error)} - ${getErrorMessage(error)}`,
                );

                if (!retryable) {
                    isRunning = false;
                    clearRestartTimer();
                    return;
                }

                scheduleRestart();
            }
        }, AUTO_RESTART_DELAY_MS);
    };

    recognition.onresult = (event) => {
        if (!isRunning || isManuallyStopped) {
            return;
        }

        for (
            let index = event.resultIndex;
            index < event.results.length;
            index += 1
        ) {
            const result = event.results[index];
            const transcript = result?.[0]?.transcript?.trim();
            if (!transcript) {
                continue;
            }

            if (result.isFinal) {
                sendTranscript(transcript);
            }
        }
    };

    recognition.onerror = (event) => {
        const message = event.error || event.message || "浏览器语音识别发生错误";
        onStatus?.(message);

        const fatalErrors = new Set([
            "not-allowed",
            "service-not-allowed",
            "audio-capture",
        ]);
        if (event.error && fatalErrors.has(event.error)) {
            isRunning = false;
            clearRestartTimer();
        }
    };

    recognition.onend = () => {
        if (!isRunning || isManuallyStopped) {
            return;
        }

        scheduleRestart();
    };

    return {
        start: async () => {
            isRunning = true;
            isManuallyStopped = false;
            clearRestartTimer();
            onStatus?.("正在启动浏览器语音识别...");
            try {
                recognition.start();
            } catch (error) {
                const errorName = getErrorName(error);
                const errorMessage = getErrorMessage(error);
                const retryable = isRetryableStartError(error);
                onStatus?.(
                    retryable
                        ? `浏览器语音启动重试中：${errorName} - ${errorMessage}`
                        : `浏览器语音启动失败：${errorName} - ${errorMessage}`,
                );

                if (!retryable) {
                    isRunning = false;
                    clearRestartTimer();
                    if (error instanceof Error) {
                        throw error;
                    }
                    throw new Error(`浏览器语音启动失败：${errorName} - ${errorMessage}`);
                }

                scheduleRestart();
            }
        },
        stop: async () => {
            isManuallyStopped = true;
            isRunning = false;
            clearRestartTimer();
            try {
                recognition.stop();
            } catch {
                try {
                    recognition.abort();
                } catch {
                    /* ignore abort errors */
                }
            }
        },
    };
}
