import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "modal-wide" : ""}`}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button className="icon-button" onClick={close} aria-label="关闭对话框">
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function RichText({ text }: { text: string }) {
  return (
    <div className="markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          img: ({ alt }) => (
            <span className="muted">[图片：{alt || "已省略"}]</span>
          ),
          a: ({ href, children }) => (
            <ExternalLink href={href}>{children}</ExternalLink>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

function ExternalLink({
  href,
  children,
}: {
  href?: string;
  children: ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  try {
    const url = new URL(href ?? "");
    if (url.protocol !== "https:" || url.username || url.password)
      return <span>{children}</span>;
  } catch {
    return <span>{children}</span>;
  }
  return (
    <>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(event) => {
          if (!("__TAURI_INTERNALS__" in window)) return;
          event.preventDefault();
          setFailed(false);
          void import("@tauri-apps/plugin-opener")
            .then(({ openUrl }) => openUrl(href!))
            .catch(() => setFailed(true));
        }}
      >
        {children}
      </a>
      {failed && (
        <span role="status" className="muted">
          （无法打开浏览器，可复制链接后重试）
        </span>
      )}
    </>
  );
}

export const shortTime = (date: string) =>
  new Date(date).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
export const shortDate = (date: string) =>
  new Date(date).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
  });
export const fileSize = (bytes: number) =>
  bytes >= 1e9
    ? `${(bytes / 1e9).toFixed(2)} GB`
    : `${Math.round(bytes / 1e6)} MB`;

export function Empty({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}
