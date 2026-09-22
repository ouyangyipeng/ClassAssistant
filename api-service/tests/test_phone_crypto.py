import json

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import JsonValue

from classfox.phone_crypto import PhoneCipher


def test_direction_counter_and_pair_identity_are_authenticated() -> None:
    cipher = PhoneCipher(bytes(range(32)), "a" * 32, bytes(range(32, 64)))
    message: dict[str, JsonValue] = {"operation": "hello", "name": "课堂手机 🦊"}
    sealed = cipher.seal("c2s", 1, message)
    assert cipher.open("c2s", 1, sealed) == message
    assert "课堂" not in sealed
    assert len(cipher.verification_code) == 6
    with pytest.raises(InvalidTag):
        cipher.open("s2c", 1, sealed)
    with pytest.raises(InvalidTag):
        cipher.open("c2s", 2, sealed)
    other = PhoneCipher(bytes(range(32)), "b" * 32, bytes(range(32, 64)))
    with pytest.raises(InvalidTag):
        other.open("c2s", 1, sealed)


@pytest.mark.parametrize("counter", [0, -1, 2**32, True])
def test_counter_outside_wire_range_is_rejected(counter: int) -> None:
    cipher = PhoneCipher(bytes(range(32)), "a" * 32, bytes(range(32, 64)))
    with pytest.raises(ValueError):
        cipher.seal("c2s", counter, {})


def test_ciphertext_tampering_and_invalid_base64_are_rejected() -> None:
    cipher = PhoneCipher(bytes(range(32)), "a" * 32, bytes(range(32, 64)))
    sealed = cipher.seal("c2s", 1, {"operation": "hello"})
    with pytest.raises(InvalidTag):
        cipher.open("c2s", 1, ("A" if sealed[0] != "A" else "B") + sealed[1:])
    with pytest.raises(ValueError):
        cipher.open("c2s", 1, "not base64!")


def test_fixed_vector_matches_javascript_fixture() -> None:
    from pathlib import Path

    vector = json.loads((Path(__file__).parents[2] / "mini-program" / "tests" / "phone-vector.json").read_text(encoding="utf-8"))
    cipher = PhoneCipher(bytes.fromhex(vector["secret"]), vector["id"], bytes.fromhex(vector["client_nonce"]))
    for direction in ["c2s", "s2c"]:
        assert cipher.open(direction, 1, vector[direction]) == vector["message"]
    assert cipher.verification_code == vector["verification_code"]
