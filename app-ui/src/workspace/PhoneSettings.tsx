import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Smartphone, ShieldCheck } from "lucide-react";
import { WorkspaceStore } from "./store";

interface PhoneConnection {
  id: string;
  name: string;
  client_nonce: string;
  state: "offered" | "pending" | "approved";
  verification_code: string | null;
  expires_in: number;
}
interface PhoneStatus {
  listening: boolean;
  address: string | null;
  port: number | null;
  connections: PhoneConnection[];
}
interface Offer {
  version: 1;
  address: string;
  port: number;
  id: string;
  secret: string;
  expires_in: number;
}

export function PhoneSettings({ store }: { store: WorkspaceStore }) {
  const [status, setStatus] = useState<PhoneStatus | null>(null);
  const [address, setAddress] = useState("");
  const [addresses, setAddresses] = useState<string[]>([]);
  const [discovery, setDiscovery] = useState("");
  const [offer, setOffer] = useState<Offer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const revision = useRef(0);
  const mutating = useRef(false);

  async function refresh(signal?: AbortSignal) {
    const version = revision.current;
    const next = await store.api.request<PhoneStatus>("/phone", { signal });
    if (
      !mounted.current ||
      signal?.aborted ||
      mutating.current ||
      version !== revision.current
    )
      return;
    setStatus(next);
    setOffer((previous) =>
      previous &&
      next.connections.some(
        (connection) =>
          connection.id === previous.id && connection.state === "offered",
      )
        ? previous
        : null,
    );
  }
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        await refresh(abort.signal);
      } catch {
        if (!abort.signal.aborted)
          setError("无法读取手机连接状态，请确认本地服务仍在运行");
      }
      if (!abort.signal.aborted) timer = setTimeout(poll, 1500);
    }
    void poll();
    void store.api
      .request<{ addresses: string[]; message: string }>("/phone/addresses", {
        signal: abort.signal,
      })
      .then((result) => {
        if (abort.signal.aborted) return;
        setAddresses(result.addresses);
        setDiscovery(result.message);
        setAddress((previous) => previous || result.addresses[0] || "");
      })
      .catch(() => {
        if (!abort.signal.aborted)
          setDiscovery("请填写系统 Wi-Fi 详情中的 IPv4 地址");
      });
    return () => {
      mounted.current = false;
      abort.abort();
      clearTimeout(timer);
    };
  }, [store]);

  async function act(action: () => Promise<unknown>) {
    if (mutating.current) return;
    mutating.current = true;
    revision.current++;
    setBusy(true);
    setError("");
    try {
      await action();
      mutating.current = false;
      revision.current++;
      await refresh();
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof Error ? failure.message : "操作未完成，请重试",
        );
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  const preferences = store.getSnapshot().settings;
  const local =
    preferences?.asr.mode === "offline" &&
    preferences.llm.mode === "local" &&
    preferences.llm.managed;
  return (
    <section className="settings-section">
      <div className="section-heading">
        <h3>微信小程序 · v2.5 开发预览</h3>
        <p>
          尚未正式发布，需自行构建小程序，真机验证将在 v2.5 完成。手机与电脑连接同一
          Wi-Fi，在课狐小程序内扫码。连接只在本次应用运行期间有效。
        </p>
      </div>
      <div className="notice">
        <ShieldCheck size={18} />
        <span>
          音频与课堂文字加密传输。手机只能操作自己的课堂；开启后仍需逐台确认，最多连接
          4 台。
        </span>
      </div>
      {!local && (
        <p className="notice">
          语音识别请选择“离线
          SenseVoice”，问答请选择应用管理的本地模型。手机连接不会使用电脑的 BYOK
          凭据。
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!status?.listening ? (
        <>
          <label>
            此电脑的 Wi-Fi IPv4 地址
            <input
              value={address}
              list="phone-addresses"
              onChange={(event) => setAddress(event.target.value)}
              placeholder="例如 192.168.1.20"
              autoComplete="off"
            />
          </label>
          <datalist id="phone-addresses">
            {addresses.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          {discovery && <p className="muted">{discovery}</p>}
          <button
            className="button primary"
            disabled={busy || !address.trim() || !status}
            onClick={() =>
              void act(() =>
                store.api.post("/phone", { address: address.trim() }),
              )
            }
          >
            <Smartphone size={17} />
            开启手机连接
          </button>
        </>
      ) : (
        <>
          <div className="row spread">
            <span className="status-pill">已开启 · {status.address}</span>
            <button
              className="button secondary small"
              disabled={busy}
              onClick={() =>
                void act(() =>
                  store.api.request("/phone", { method: "DELETE" }),
                )
              }
            >
              关闭所有手机连接
            </button>
          </div>
          <button
            className="button primary"
            disabled={
              busy ||
              status.connections.filter(
                (connection) => connection.state === "approved",
              ).length >= 4
            }
            onClick={() =>
              void act(async () => {
                const next = await store.api.post<Offer>("/phone/offers");
                if (mounted.current) setOffer(next);
              })
            }
          >
            生成配对二维码
          </button>
          {offer && (
            <div className="phone-qr">
              <QRCodeSVG
                value={"classfox-pair-v1:" + JSON.stringify(offer)}
                size={240}
                marginSize={4}
                level="M"
                title="在课狐小程序内扫描此配对码"
              />
              <div>
                <strong>在课狐小程序内扫码</strong>
                <p>二维码 2 分钟内有效，只能配对一台手机。请勿截图转发。</p>
              </div>
            </div>
          )}
          {status.connections
            .filter((connection) => connection.state !== "offered")
            .map((connection) => (
              <article className="phone-connection" key={connection.id}>
                <div>
                  <strong>{connection.name}</strong>
                  <p className="muted">
                    {connection.state === "approved"
                      ? "已允许 · 关闭或退出电脑应用后失效"
                      : "核对手机上的 6 位数字，确认一致后允许连接"}
                  </p>
                </div>
                {connection.state === "pending" && (
                  <>
                    <output className="pairing-code" aria-label="配对核对数字">
                      {connection.verification_code}
                    </output>
                    <button
                      className="button primary small"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          store.api.post(`/phone/${connection.id}/approve`, {
                            client_nonce: connection.client_nonce,
                          }),
                        )
                      }
                    >
                      数字一致，允许连接
                    </button>
                  </>
                )}
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    void act(() =>
                      store.api.request(`/phone/${connection.id}`, {
                        method: "DELETE",
                      }),
                    )
                  }
                >
                  {connection.state === "pending" ? "拒绝" : "撤销连接"}
                </button>
              </article>
            ))}
          <p className="muted">
            电脑需保持运行。校园网若隔离设备，可改用手机热点连接；微信正式使用仍需小程序
            AppID 和真机配置。
          </p>
        </>
      )}
    </section>
  );
}
