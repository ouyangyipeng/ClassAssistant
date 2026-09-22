import { describe, expect, it } from "vitest";
import {
  PhoneCipher,
  fromHex,
  fromUtf8,
  utf8,
  type BinaryCodec,
  type Direction,
} from "../src/core/phoneCrypto";
import vector from "./phone-vector.json";

const codec: BinaryCodec = {
  toBase64: (bytes) => Buffer.from(bytes).toString("base64"),
  fromBase64: (value) => {
    if (
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
        value,
      )
    )
      throw new Error("Invalid base64");
    return new Uint8Array(Buffer.from(value, "base64"));
  },
};

describe("phone encryption interoperability", () => {
  const create = () =>
    new PhoneCipher(
      fromHex(vector.secret, 32),
      vector.id,
      fromHex(vector.client_nonce, 32),
      codec,
    );
  it("matches independent Node crypto and Python vectors in both directions", () => {
    const cipher = create();
    for (const direction of ["c2s", "s2c"] as Direction[]) {
      expect(cipher.seal(direction, 1, vector.message)).toBe(vector[direction]);
      expect(cipher.open(direction, 1, vector[direction])).toEqual(
        vector.message,
      );
    }
    expect(cipher.verificationCode).toBe(vector.verification_code);
  });
  it("rejects changes to ciphertext, direction and counter", () => {
    const cipher = create();
    expect(() => cipher.open("s2c", 1, vector.c2s)).toThrow();
    expect(() => cipher.open("c2s", 2, vector.c2s)).toThrow();
    const altered = (vector.c2s[0] === "A" ? "B" : "A") + vector.c2s.slice(1);
    expect(() => cipher.open("c2s", 1, altered)).toThrow();
    for (const counter of [0, -1, 1.5, 2 ** 32])
      expect(() => cipher.seal("c2s", counter, {})).toThrow();
  });
  it("handles UTF-8 independently of browser globals and fails on malformed text", () => {
    for (const text of ["", "课堂 🦊\n重点", "a%+! é\u0000"])
      expect(fromUtf8(utf8(text))).toBe(text);
    expect(() => fromUtf8(new Uint8Array([255]))).toThrow();
  });
});
