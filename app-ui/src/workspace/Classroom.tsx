import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUpRight,
  BookOpen,
  FileText,
  FileUp,
  Headphones,
  MessageSquare,
  Mic,
  Plus,
  Search,
  Send,
  Sparkles,
  Square,
  Upload,
  WandSparkles,
} from "lucide-react";
import { saveText } from "./client";
import {
  isRunning,
  jobLabel,
  type ChatMessage,
  type Job,
  type JobKind,
  type Material,
  type Session,
  type Source,
} from "./domain";
import { Empty, Modal, RichText, shortDate, shortTime } from "./primitives";
import { WorkspaceStore, type WorkspaceState } from "./store";

export function Welcome({
  begin,
  settings,
}: {
  begin: () => void;
  settings: () => void;
}) {
  return (
    <div className="welcome">
      <span className="eyebrow">CLASSFOX · 课狐</span>
      <h1>
        把注意力
        <br />
        留给课堂。
      </h1>
      <p>
        留下完整原文，随时跟上进度。
        <br />
        需要回答时，让课狐帮你理清思路。
      </p>
      <div className="welcome-actions">
        <button className="button" onClick={begin}>
          <Plus size={17} />
          开始第一堂课
        </button>
        <button className="button secondary" onClick={settings}>
          配置模型 <ArrowUpRight size={16} />
        </button>
      </div>
      <div className="welcome-steps">
        <div>
          <span>01</span>
          <Mic size={20} />
          <h3>听见课堂</h3>
          <p>
            离线识别或自带云端密钥，
            <br />
            也可以直接输入文字。
          </p>
        </div>
        <div>
          <span>02</span>
          <Sparkles size={20} />
          <h3>随时接上</h3>
          <p>
            查看实时原文，
            <br />
            救场、追问、找回重点。
          </p>
        </div>
        <div>
          <span>03</span>
          <BookOpen size={20} />
          <h3>留下收获</h3>
          <p>
            按课堂保存历史，
            <br />
            整理笔记并导出。
          </p>
        </div>
      </div>
      <p className="welcome-footnote">本地模式下，课堂内容在你的电脑上处理。</p>
    </div>
  );
}

export function StartClass({
  store,
  state,
  close,
  start,
  cancel,
}: {
  store: WorkspaceStore;
  state: WorkspaceState;
  close: () => void;
  cancel: () => Promise<void>;
  start: (
    name: string,
    source: Source,
    material: string | null,
  ) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [material, setMaterial] = useState("");
  const [source, setSource] = useState<Source>(
    state.settings?.asr.mode === "webspeech" ? "browser" : "microphone",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await start(name.trim() || "未命名课堂", source, material || null);
      close();
    } catch (error) {
      setError(error instanceof Error ? error.message : "无法开始课堂");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="开始一堂课" close={close}>
      <form className="start-form" onSubmit={(event) => void submit(event)}>
        <label>
          课程名称
          <input
            autoFocus
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：数据结构 · 二叉树"
          />
        </label>
        <label>
          记录方式
          <select
            value={source}
            onChange={(event) => setSource(event.target.value as Source)}
          >
            <option value="microphone">麦克风 · 当前语音服务</option>
            <option value="browser">浏览器语音识别</option>
            <option value="text">文本输入 · 无需麦克风</option>
            <option value="remote">上传音频片段</option>
          </select>
        </label>
        <label>
          本堂课的参考资料
          <select
            value={material}
            onChange={(event) => setMaterial(event.target.value)}
          >
            <option value="">暂不使用资料</option>
            {state.materials.map((item) => (
              <option key={item.id} value={item.id}>
                {item.filename}
              </option>
            ))}
          </select>
        </label>
        <p className="field-help">
          每堂课单独保存原文。录音前请确认已获得课堂参与者的知情同意。
        </p>
        {source === "browser" && (
          <p className="notice">
            浏览器语音能力取决于当前
            WebView，通常需要联网。不支持时可以切换到离线或文本输入。
          </p>
        )}
        {source === "remote" && (
          <p className="notice">
            支持每段最多 30 秒的 16 kHz、单声道、16 位 PCM WAV 音频。
          </p>
        )}
        {error && (
          <p role="alert" className="notice error">
            {error}
          </p>
        )}
        <div className="modal-footer">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={close}
          >
            取消
          </button>
          <button className="button" disabled={busy || !!state.current}>
            {busy ? "正在检查并准备…" : "开始记录"}
          </button>
        </div>
        {state.current?.status === "error" && (
          <button
            type="button"
            className="text-button"
            onClick={() =>
              void store.action(async () => {
                await store.api.post(`/sessions/${state.current!.id}/stop`);
                await store.refresh();
                setError(null);
              })
            }
          >
            结束未成功启动的课堂，重新选择输入方式
          </button>
        )}
        {busy && state.current?.status === "starting" && (
          <button
            type="button"
            className="button secondary"
            disabled={state.stopping}
            onClick={() => void cancel()}
          >
            {state.stopping ? "正在取消启动…" : "取消语音启动"}
          </button>
        )}
      </form>
    </Modal>
  );
}

export function Transcript({
  store,
  state,
  session,
}: {
  store: WorkspaceStore;
  state: WorkspaceState;
  session: Session;
}) {
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [following, setFollowing] = useState(true);
  const scroll = useRef<HTMLDivElement>(null);
  const isCurrent =
    state.current?.id === session.id && session.status === "recording";
  const items = state.entries.filter((entry) =>
    entry.text.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  useEffect(() => {
    if (following && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [state.entries, state.partial, following]);
  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    await store.action(async () => {
      await store.api.post(`/sessions/${session.id}/entries`, {
        text: text.trim(),
        source_id: crypto.randomUUID(),
      });
      setText("");
      await store.loadSelection();
    });
  };
  return (
    <div className="transcript-pane">
      <div className="transcript-toolbar">
        <span>{state.entries.length} 段原文</span>
        <label className="search-box">
          <Search size={15} />
          <input
            aria-label="搜索课堂原文"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="查找原文"
          />
        </label>
      </div>
      <div
        className="transcript-scroll"
        ref={scroll}
        onScroll={() => {
          const node = scroll.current;
          if (node)
            setFollowing(
              node.scrollHeight - node.scrollTop - node.clientHeight < 70,
            );
        }}
      >
        {state.selectionLoading ? (
          <p className="loading-text">正在读取课堂记录…</p>
        ) : !items.length ? (
          <Empty
            icon={<Headphones size={25} />}
            title={query ? "没有匹配的原文" : "课堂原文会出现在这里"}
          >
            <p>
              {isCurrent
                ? "开始说话，或在下方输入课堂文字。"
                : "这堂课暂时没有记录。"}
            </p>
          </Empty>
        ) : (
          <div className="transcript-list">
            {items.map((entry) => (
              <article key={entry.id} className="transcript-entry">
                <time dateTime={entry.created_at}>
                  {shortTime(entry.created_at)}
                </time>
                <p>
                  {highlight(entry.text, [
                    ...(state.settings?.keywords ?? []),
                    ...(state.settings?.warning_keywords ?? []),
                  ])}
                </p>
              </article>
            ))}
          </div>
        )}
        {state.partial && isCurrent && (
          <div className="partial-transcript">
            <span className="live-dot" />
            {state.partial}
            <span className="muted"> · 识别中</span>
          </div>
        )}
      </div>
      {!following && (
        <button className="latest-button" onClick={() => setFollowing(true)}>
          <ArrowDown size={14} />
          回到最新
        </button>
      )}
      {isCurrent && (
        <form className="manual-input" onSubmit={(event) => void send(event)}>
          <label htmlFor="classroom-text">
            补充课堂文字 <span>可使用系统输入法语音输入</span>
          </label>
          <div className="manual-input-row">
            <textarea
              id="classroom-text"
              rows={2}
              maxLength={8000}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="粘贴或输入老师刚才说的话…"
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  void send(event);
                }
              }}
            />
            <button
              className="icon-button primary"
              disabled={!text.trim() || state.busy}
              aria-label="保存课堂文字"
            >
              <Send size={17} />
            </button>
          </div>
          {state.source === "remote" && (
            <label className="audio-upload">
              <Upload size={14} />
              上传 WAV 片段
              <input
                type="file"
                accept=".wav,audio/wav"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  void store.action(async () => {
                    const form = new FormData();
                    form.set("file", file);
                    form.set("source_id", crypto.randomUUID());
                    await store.api.request(`/sessions/${session.id}/audio`, {
                      method: "POST",
                      body: form,
                      timeout: 180000,
                    });
                    await store.loadSelection();
                  });
                }}
              />
            </label>
          )}
        </form>
      )}
    </div>
  );
}

function highlight(text: string, keywords: string[]) {
  const terms = keywords
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!terms.length) return text;
  const expression = new RegExp(`(${terms.join("|")})`, "gi");
  return text
    .split(expression)
    .map((part, index) => (index % 2 ? <mark key={index}>{part}</mark> : part));
}

export function AssistantPane({
  store,
  state,
  session,
}: {
  store: WorkspaceStore;
  state: WorkspaceState;
  session: Session;
}) {
  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const jobs = [...state.jobs].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );
  const job = jobs.find((item) => item.id === selected) ?? jobs[0];
  async function ask(kind: JobKind) {
    await store.action(async () => {
      const history: ChatMessage[] =
        job?.status === "completed"
          ? [
              {
                role: "user",
                content: questions[job.id] || jobLabel[job.kind],
              },
              { role: "assistant", content: job.markdown.slice(-4000) },
            ]
          : [];
      const result = await store.api.post<Job>(
        `/sessions/${session.id}/assistant`,
        { kind, question: kind === "followup" ? question.trim() : "", history },
      );
      if (kind === "followup")
        setQuestions((previous) => ({
          ...previous,
          [result.id]: question.trim(),
        }));
      setSelected(result.id);
      setQuestion("");
      await store.fetchJob(result.id);
    });
  }
  return (
    <aside className="assistant-pane">
      <header className="assistant-heading">
        <div>
          <span className="assistant-symbol">
            <Sparkles size={17} />
          </span>
          <h2>课堂助手</h2>
        </div>
        <span className="muted">
          {state.settings?.llm.mode === "local" ? "本地模型" : "云端 BYOK"}
        </span>
      </header>
      <div className="quick-actions">
        <button
          className="rescue-action"
          disabled={
            state.busy ||
            jobs.some((job) => job.kind === "rescue" && isRunning(job))
          }
          onClick={() => void ask("rescue")}
        >
          <WandSparkles size={19} />
          <span>
            帮我救场<small>先给出能说出口的答案</small>
          </span>
          <ArrowUpRight size={16} />
        </button>
        <button
          className="catchup-action"
          disabled={
            state.busy ||
            jobs.some((job) => job.kind === "catchup" && isRunning(job))
          }
          onClick={() => void ask("catchup")}
        >
          <BookOpen size={18} />
          讲到哪里了 <ArrowUpRight size={15} />
        </button>
      </div>
      <div className="answer-space">
        {job ? (
          <>
            <div className="answer-heading">
              <span className="eyebrow">{jobLabel[job.kind]}</span>
              <div className="row">
                {isRunning(job) && (
                  <button
                    className="text-button"
                    onClick={() =>
                      void store.action(async () => {
                        await store.api.request(`/assistant/${job.id}`, {
                          method: "DELETE",
                        });
                        await store.fetchJob(job.id);
                      })
                    }
                  >
                    <Square size={11} />
                    停止
                  </button>
                )}
                {job.markdown && (
                  <button
                    className="text-button"
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(job.markdown)
                        .catch((error) => store.report(error))
                    }
                  >
                    复制
                  </button>
                )}
              </div>
            </div>
            {questions[job.id] && (
              <p className="user-question">{questions[job.id]}</p>
            )}
            {job.markdown ? (
              <RichText text={job.markdown} />
            ) : (
              <p className="answer-placeholder">
                {isRunning(job)
                  ? job.stage + "…"
                  : job.error_message || "此次没有生成内容"}
              </p>
            )}
            {isRunning(job) && (
              <span className="generating" role="status">
                <span className="live-dot" />
                {job.stage}
              </span>
            )}
            {job.error_message && (
              <p role="alert" className="notice error">
                {job.error_message}
              </p>
            )}
            {job.status === "cancelled" && (
              <p className="field-help">已取消。上方保留的是尚未完成的回答。</p>
            )}
            {job.first_token_ms !== null && (
              <div className="answer-metrics">
                首字 {(job.first_token_ms / 1000).toFixed(1)} 秒
                {job.total_ms !== null &&
                  ` · 用时 ${(job.total_ms / 1000).toFixed(1)} 秒`}
              </div>
            )}
          </>
        ) : (
          <Empty
            icon={<MessageSquare size={24} />}
            title="听懂这一段，再接着往下"
          >
            <p>
              救场、回顾进度，或问一个具体问题。
              <br />
              回答会结合本堂课的原文和资料。
            </p>
          </Empty>
        )}
      </div>
      {jobs.length > 1 && (
        <label className="answer-history">
          此前的回答
          <select
            aria-label="选择此前的回答"
            value={job?.id ?? ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {jobs.map((item) => (
              <option key={item.id} value={item.id}>
                {shortTime(item.created_at)} · {jobLabel[item.kind]}
              </option>
            ))}
          </select>
        </label>
      )}
      <form
        className="question-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void ask("followup");
        }}
      >
        <textarea
          aria-label="向课堂助手追问"
          rows={2}
          maxLength={4000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="例如：用一个例子解释刚才的概念"
        />
        <div>
          <span>结合当前课堂回答</span>
          <button
            className="icon-button primary"
            disabled={!question.trim() || state.busy}
            aria-label="发送追问"
          >
            <Send size={16} />
          </button>
        </div>
      </form>
    </aside>
  );
}

export function NotesPane({
  store,
  state,
  session,
}: {
  store: WorkspaceStore;
  state: WorkspaceState;
  session: Session;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const note =
    state.notes.find((note) => note.id === selected) ?? state.notes[0];
  const running = state.jobs.some(
    (job) => job.kind === "summary" && isRunning(job),
  );
  const summary = async () => {
    await store.action(async () => {
      const job = await store.api.post<Job>(
        `/sessions/${session.id}/assistant`,
        { kind: "summary" },
      );
      await store.fetchJob(job.id);
    });
  };
  return (
    <div className="notes-pane">
      <div className="notes-toolbar">
        <span className="muted">
          {state.notes.length
            ? `${state.notes.length} 份整理结果 · 原文始终保留`
            : "按完整课堂原文整理"}
        </span>
        <button
          className="button secondary small"
          disabled={!state.entries.length || running || state.busy}
          onClick={() => void summary()}
        >
          <Sparkles size={14} />
          {running ? "正在整理…" : "整理笔记"}
        </button>
      </div>
      {note ? (
        <div className="note-document">
          <div className="row spread">
            <select
              aria-label="笔记版本"
              value={note.id}
              onChange={(event) => setSelected(event.target.value)}
            >
              {state.notes.map((item) => (
                <option key={item.id} value={item.id}>
                  {shortDate(item.created_at)} {shortTime(item.created_at)}
                </option>
              ))}
            </select>
            <button
              className="text-button"
              onClick={() =>
                void store.action(async () => {
                  const text = await store.api.request<string>(
                    `/summaries/${note.id}/export`,
                    { text: true },
                  );
                  await saveText(text, "课堂笔记.md");
                })
              }
            >
              导出 Markdown
            </button>
          </div>
          <RichText text={note.markdown} />
        </div>
      ) : (
        <Empty
          icon={<FileText size={25} />}
          title={running ? "正在整理这堂课" : "把一堂课整理成笔记"}
        >
          <p>
            {running
              ? "可以在右侧查看生成进度，也可以继续浏览原文。"
              : "原文和资料已经准备好后，点击整理笔记。"}
          </p>
        </Empty>
      )}
    </div>
  );
}

export function MaterialsPane({
  store,
  materials,
}: {
  store: WorkspaceStore;
  materials: Material[];
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <section className="library-pane">
      <div className="section-heading row spread">
        <div>
          <span className="eyebrow">COURSE LIBRARY</span>
          <h1>课程资料</h1>
          <p>开始课堂时选择一份资料，回答与笔记就能参考其中的内容。</p>
        </div>
        <button className="button" onClick={() => input.current?.click()}>
          <FileUp size={17} />
          上传资料
        </button>
      </div>
      <input
        hidden
        ref={input}
        type="file"
        accept=".pdf,.pptx,.docx,.txt,.md"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          void store.action(async () => {
            if (file.size > 25 * 1024 * 1024)
              throw new Error("资料不能超过 25 MiB，请拆分后上传");
            const form = new FormData();
            form.set("file", file);
            await store.api.request("/materials", {
              method: "POST",
              body: form,
              timeout: 60000,
            });
            await store.refresh();
          });
        }}
      />
      <p className="field-help">
        支持 PDF、PPTX、DOCX、TXT、Markdown，单份最多 25 MiB。扫描 PDF
        需要先进行文字识别；旧版 PPT / DOC 请先转换格式。
      </p>
      {materials.length ? (
        <div className="material-list">
          {materials.map((item) => (
            <article key={item.id}>
              <span className="file-icon">
                <FileText size={21} />
              </span>
              <div>
                <h3>{item.filename}</h3>
                <p>
                  {item.characters.toLocaleString()} 字符 ·{" "}
                  {shortDate(item.created_at)}
                </p>
              </div>
              <span className="badge">已解析</span>
            </article>
          ))}
        </div>
      ) : (
        <Empty icon={<FileUp size={27} />} title="从一份讲义开始">
          <p>添加课件、讲义或课程大纲。</p>
        </Empty>
      )}
    </section>
  );
}
