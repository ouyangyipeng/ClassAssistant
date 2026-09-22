import base64
import json
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import JsonValue

Direction = Literal["c2s", "s2c"]
MAX_PLAINTEXT = 700 * 1024


class MessageTooLarge(ValueError):
    pass


class PhoneCipher:
    def __init__(self, secret: bytes, pair_id: str, client_nonce: bytes) -> None:
        if len(secret) != 32 or len(client_nonce) != 32 or len(pair_id) != 32 or any(char not in "0123456789abcdef" for char in pair_id):
            raise ValueError("Invalid pairing material")
        self.pair_id = pair_id
        self._ciphers = {direction: AESGCM(self._derive(secret, client_nonce, direction)) for direction in ("c2s", "s2c")}
        verification = self._derive(secret, client_nonce, "verification")
        self.verification_code = f"{int.from_bytes(verification[:4], 'big') % 1_000_000:06d}"

    def _derive(self, secret: bytes, salt: bytes, purpose: str) -> bytes:
        info = f"classfox-phone-v1|{self.pair_id}|{purpose}".encode("ascii")
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(secret)

    def _parameters(self, direction: Direction, counter: int) -> tuple[bytes, bytes]:
        if type(counter) is not int or not 1 <= counter < 2**32:
            raise ValueError("Invalid message counter")
        return counter.to_bytes(12, "big"), f"classfox-phone-v1|{self.pair_id}|{direction}|{counter}".encode("ascii")

    def seal(self, direction: Direction, counter: int, message: dict[str, JsonValue]) -> str:
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > MAX_PLAINTEXT:
            raise MessageTooLarge("Message too large")
        nonce, aad = self._parameters(direction, counter)
        return base64.b64encode(self._ciphers[direction].encrypt(nonce, raw, aad)).decode("ascii")

    def open(self, direction: Direction, counter: int, ciphertext: str) -> dict[str, JsonValue]:
        if len(ciphertext) > (MAX_PLAINTEXT + 16) * 4 // 3 + 4:
            raise ValueError("Message too large")
        sealed = base64.b64decode(ciphertext, validate=True)
        nonce, aad = self._parameters(direction, counter)
        raw = self._ciphers[direction].decrypt(nonce, sealed, aad)
        message = json.loads(raw, parse_constant=lambda _value: invalid_constant())
        if not isinstance(message, dict):
            raise ValueError("Invalid message")
        return message


def invalid_constant() -> None:
    raise ValueError("Invalid JSON number")
