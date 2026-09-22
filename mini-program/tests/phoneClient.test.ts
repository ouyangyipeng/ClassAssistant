import { describe, expect, it } from "vitest";
import {
  PhoneClient,
  PhoneTransportError,
  parsePairing,
  type Envelope,
  type PairOffer,
} from "../src/core/phoneClient";
import {
  PhoneCipher,
  fromHex,
  type BinaryCodec,
} from "../src/core/phoneCrypto";
import vector from "./phone-vector.json";

const codec: BinaryCodec = {
  toBase64: (bytes) => Buffer.from(bytes).toString("base64"),
  fromBase64: (value) => new Uint8Array(Buffer.from(value, "base64")),
};
const offer: PairOffer = {
  version: 1,
  address: "192.168.1.20",
  port: 40001,
  id: vector.id,
  secret: vector.secret,
  expires_in: 120,
};
const cipher = () =>
  new PhoneCipher(
    fromHex(offer.secret, 32),
    offer.id,
    fromHex(vector.client_nonce, 32),
    codec,
  );

describe("serialized encrypted phone channel", () => {
  it("retires a channel if encoding throws after encryption, so its nonce is never reused", async () => {
    let encryptions = 0,
      requests = 0;
    const failingCodec: BinaryCodec = {
      ...codec,
      toBase64() {
        encryptions++;
        throw new Error("synthetic native encoding failure");
      },
    };
    const client = new PhoneClient(
      offer,
      fromHex(vector.client_nonce, 32),
      failingCodec,
      async () => {
        requests++;
        return {};
      },
    );
    await expect(client.request({ operation: "status" })).rejects.toThrow(
      "校验失败",
    );
    expect(client.connected).toBe(false);
    await expect(
      client.request({
        operation: "create",
        course_name: "different plaintext",
      }),
    ).rejects.toThrow("失效");
    expect(encryptions).toBe(1);
    expect(requests).toBe(0);
  });
  it("retries exactly the same bytes, then increments queued requests once", async () => {
    const received: Envelope[] = [];
    const server = cipher();
    const client = new PhoneClient(
      offer,
      fromHex(vector.client_nonce, 32),
      codec,
      async (_url, request) => {
        received.push(request);
        if (received.length === 1)
          throw new PhoneTransportError("Synthetic dropped response");
        return {
          version: 1,
          counter: request.counter,
          ciphertext: server.seal("s2c", request.counter, { ok: true }),
        };
      },
    );
    await Promise.all([
      client.request({ operation: "status" }),
      client.request({ operation: "create", course_name: "中文 🦊" }),
    ]);
    expect(received[0]).toBe(received[1]);
    expect(received.map((request) => request.counter)).toEqual([1, 1, 2]);
    expect(server.open("c2s", 2, received[2].ciphertext)).toEqual({
      operation: "create",
      course_name: "中文 🦊",
    });
  });
  it("consumes an encrypted application error but retires uncertain channels", async () => {
    const server = cipher();
    let calls = 0;
    const client = new PhoneClient(
      offer,
      fromHex(vector.client_nonce, 32),
      codec,
      async (_url, request) => {
        calls++;
        if (calls > 1) throw new PhoneTransportError("Lost", false);
        return {
          version: 1,
          counter: 1,
          ciphertext: server.seal("s2c", request.counter, {
            error: "pending_approval",
            message: "等待确认",
          }),
        };
      },
    );
    await expect(client.request({ operation: "create" })).rejects.toThrow(
      "等待确认",
    );
    await expect(client.request({ operation: "status" })).rejects.toThrow(
      "连接已中断",
    );
    await expect(client.request({ operation: "status" })).rejects.toThrow(
      "已失效",
    );
    expect(calls).toBe(2);
  });
  it("rejects wrong response counters and public or malformed QR endpoints", async () => {
    const client = new PhoneClient(
      offer,
      fromHex(vector.client_nonce, 32),
      codec,
      async () => ({ version: 1, counter: 2, ciphertext: vector.s2c }),
    );
    await expect(client.request({ operation: "status" })).rejects.toThrow(
      "校验失败",
    );
    expect(parsePairing("classfox-pair-v1:" + JSON.stringify(offer))).toEqual(
      offer,
    );
    for (const address of [
      "127.0.0.1",
      "8.8.8.8",
      "192.168.01.2",
      "192.168.1.2/path",
      "evil.example",
    ]) {
      expect(() =>
        parsePairing(
          "classfox-pair-v1:" + JSON.stringify({ ...offer, address }),
        ),
      ).toThrow();
    }
  });
});
