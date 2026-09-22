import { gcm } from "@noble/ciphers/aes.js";
import { hkdf } from "@noble/hashes/hkdf.js";
import { sha256 } from "@noble/hashes/sha2.js";

export type Direction = "c2s" | "s2c";
export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export interface BinaryCodec {
  toBase64(bytes: Uint8Array): string;
  fromBase64(value: string): Uint8Array;
}

// WeChat's logic runtime does not guarantee the browser TextEncoder globals.
export function utf8(value: string): Uint8Array {
  const binary = encodeURIComponent(value).replace(
    /%([0-9A-F]{2})/g,
    (_, hex: string) => String.fromCharCode(parseInt(hex, 16)),
  );
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function fromUtf8(bytes: Uint8Array): string {
  return decodeURIComponent(
    Array.from(
      bytes,
      (value) => `%${value.toString(16).padStart(2, "0")}`,
    ).join(""),
  );
}

export function fromHex(value: string, length: number): Uint8Array {
  if (value.length !== length * 2 || !/^[a-f0-9]+$/.test(value))
    throw new Error("配对信息格式无效");
  return Uint8Array.from(value.match(/../g)!, (pair) => parseInt(pair, 16));
}

export function toHex(value: Uint8Array): string {
  return Array.from(value, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export class PhoneCipher {
  readonly verificationCode: string;
  private keys: Record<Direction, Uint8Array>;
  private destroyed = false;

  constructor(
    secret: Uint8Array,
    private id: string,
    clientNonce: Uint8Array,
    private codec: BinaryCodec,
  ) {
    if (
      secret.length !== 32 ||
      clientNonce.length !== 32 ||
      !/^[a-f0-9]{32}$/.test(id)
    )
      throw new Error("配对信息格式无效");
    const derive = (purpose: string) =>
      hkdf(
        sha256,
        secret,
        clientNonce,
        utf8(`classfox-phone-v1|${id}|${purpose}`),
        32,
      );
    this.keys = { c2s: derive("c2s"), s2c: derive("s2c") };
    const verification = derive("verification");
    this.verificationCode = (
      new DataView(verification.buffer, verification.byteOffset, 4).getUint32(
        0,
      ) % 1000000
    )
      .toString()
      .padStart(6, "0");
    verification.fill(0);
  }

  private parameters(
    direction: Direction,
    counter: number,
  ): { nonce: Uint8Array; aad: Uint8Array } {
    if (this.destroyed) throw new Error("连接已关闭");
    if (!Number.isInteger(counter) || counter < 1 || counter >= 2 ** 32)
      throw new Error("连接计数无效，请重新配对");
    const nonce = new Uint8Array(12);
    new DataView(nonce.buffer).setUint32(8, counter);
    return {
      nonce,
      aad: utf8(`classfox-phone-v1|${this.id}|${direction}|${counter}`),
    };
  }

  seal(
    direction: Direction,
    counter: number,
    message: Record<string, Json>,
  ): string {
    const raw = utf8(JSON.stringify(message));
    if (raw.length > 700 * 1024) throw new Error("片段过大，请缩短后重试");
    const { nonce, aad } = this.parameters(direction, counter);
    return this.codec.toBase64(
      gcm(this.keys[direction], nonce, aad).encrypt(raw),
    );
  }

  open(
    direction: Direction,
    counter: number,
    ciphertext: string,
  ): Record<string, Json> {
    if (ciphertext.length > Math.floor(((700 * 1024 + 16) * 4) / 3) + 4)
      throw new Error("响应过大，连接已停止");
    const { nonce, aad } = this.parameters(direction, counter);
    const raw = gcm(this.keys[direction], nonce, aad).decrypt(
      this.codec.fromBase64(ciphertext),
    );
    const result: unknown = JSON.parse(fromUtf8(raw));
    if (!result || typeof result !== "object" || Array.isArray(result))
      throw new Error("电脑返回格式无效");
    return result as Record<string, Json>;
  }

  destroy(): void {
    this.destroyed = true;
    this.keys.c2s.fill(0);
    this.keys.s2c.fill(0);
  }
}
