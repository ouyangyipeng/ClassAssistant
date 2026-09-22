import {
  PhoneCipher,
  fromHex,
  toHex,
  type BinaryCodec,
  type Json,
} from "./phoneCrypto";

export interface Envelope {
  version: 1;
  id: string;
  client_nonce: string;
  counter: number;
  ciphertext: string;
}
export interface PairOffer {
  version: 1;
  address: string;
  port: number;
  id: string;
  secret: string;
  expires_in: number;
}
export type PhoneTransport = (
  url: string,
  envelope: Envelope,
) => Promise<unknown>;
export class PhoneTransportError extends Error {
  constructor(
    message: string,
    readonly retryable = true,
  ) {
    super(message);
  }
}
export class PhoneApplicationError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
  }
}

export function parsePairing(text: string): PairOffer {
  const prefix = "classfox-pair-v1:";
  if (!text.startsWith(prefix) || text.length > 2048)
    throw new Error("请扫描课狐电脑端显示的配对二维码");
  let value: unknown;
  try {
    value = JSON.parse(text.slice(prefix.length));
  } catch {
    throw new Error("二维码内容无效，请在电脑重新生成");
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("配对信息格式无效");
  const offer = value as Record<string, unknown>;
  if (
    Object.keys(offer).some(
      (key) =>
        !["version", "address", "port", "id", "secret", "expires_in"].includes(
          key,
        ),
    ) ||
    offer.version !== 1 ||
    typeof offer.id !== "string" ||
    !/^[a-f0-9]{32}$/.test(offer.id) ||
    typeof offer.secret !== "string" ||
    !/^[a-f0-9]{64}$/.test(offer.secret) ||
    typeof offer.port !== "number" ||
    !Number.isInteger(offer.port) ||
    offer.port < 1 ||
    offer.port > 65535 ||
    typeof offer.address !== "string" ||
    !privateAddress(offer.address)
  )
    throw new Error("配对信息格式无效");
  return {
    version: 1,
    id: offer.id,
    secret: offer.secret,
    address: offer.address,
    port: offer.port,
    expires_in: 120,
  };
}

function privateAddress(address: string): boolean {
  const parts = address.split(".");
  if (
    parts.length !== 4 ||
    parts.some(
      (part) => !/^(0|[1-9][0-9]{0,2})$/.test(part) || Number(part) > 255,
    )
  )
    return false;
  const [a, b] = parts.map(Number);
  return (
    a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
  );
}

export class PhoneClient {
  readonly verificationCode: string;
  private cipher: PhoneCipher;
  private counter = 0;
  private closed = false;
  private tail: Promise<unknown> = Promise.resolve();
  private url: string;
  private nonce: string;
  private id: string;

  constructor(
    offer: PairOffer,
    clientNonce: Uint8Array,
    codec: BinaryCodec,
    private transport: PhoneTransport,
  ) {
    offer = parsePairing("classfox-pair-v1:" + JSON.stringify(offer));
    if (clientNonce.length !== 32)
      throw new Error("无法生成安全连接，请更新微信后重试");
    const secret = fromHex(offer.secret, 32);
    this.cipher = new PhoneCipher(secret, offer.id, clientNonce, codec);
    secret.fill(0);
    this.id = offer.id;
    this.nonce = toHex(clientNonce);
    this.url = `http://${offer.address}:${offer.port}/phone/v1`;
    this.verificationCode = this.cipher.verificationCode;
  }

  get connectionId(): string {
    return this.id;
  }
  get connected(): boolean {
    return !this.closed;
  }

  request(message: Record<string, Json>): Promise<Record<string, Json>> {
    // Capture immutable input before a caller can mutate a queued audio or command.
    const snapshot = JSON.parse(JSON.stringify(message)) as Record<
      string,
      Json
    >;
    const result = this.tail.then(() => this.exchange(snapshot));
    this.tail = result.catch(() => undefined);
    return result;
  }

  async hello(name: string): Promise<void> {
    const result = await this.request({ operation: "hello", name });
    if (
      result.verification_code !== this.verificationCode ||
      result.state !== "pending"
    ) {
      this.close();
      throw new Error("电脑配对校验失败，请重新扫码");
    }
  }

  private async exchange(
    message: Record<string, Json>,
  ): Promise<Record<string, Json>> {
    if (this.closed) throw new Error("电脑连接已失效，请重新配对");
    const counter = this.counter + 1;
    try {
      const envelope: Envelope = Object.freeze({
        version: 1,
        id: this.id,
        client_nonce: this.nonce,
        counter,
        ciphertext: this.cipher.seal("c2s", counter, message),
      });
      const response = await this.send(envelope);
      if (this.closed || !response || typeof response !== "object")
        throw new Error("无效响应");
      const wire = response as Record<string, unknown>;
      if (
        wire.version !== 1 ||
        wire.counter !== counter ||
        typeof wire.ciphertext !== "string"
      )
        throw new Error("无效响应");
      const result = this.cipher.open("s2c", counter, wire.ciphertext);
      this.counter = counter;
      if (typeof result.error === "string")
        throw new PhoneApplicationError(
          typeof result.message === "string" ? result.message : "请求未完成",
          result.error,
        );
      return result;
    } catch (error) {
      if (error instanceof PhoneApplicationError) throw error;
      this.close();
      throw new Error(
        "电脑连接已中断或校验失败；已保存的原文不受影响，请重新配对",
      );
    }
  }

  private async send(envelope: Envelope): Promise<unknown> {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (this.closed) throw new Error("连接已关闭");
      try {
        return await this.transport(this.url, envelope);
      } catch (error) {
        if (
          !(error instanceof PhoneTransportError) ||
          !error.retryable ||
          attempt === 2
        )
          throw error;
      }
    }
    throw new Error("电脑未响应");
  }

  close(): void {
    this.closed = true;
    this.cipher.destroy();
  }
}
