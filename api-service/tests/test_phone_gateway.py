import json
from pathlib import Path

import httpx
import pytest

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.phone_gateway import PhoneGateway
from tests.test_audio_runtime import NoCredentials


async def test_gateway_is_opt_in_and_never_exposes_desktop_routes(tmp_path: Path) -> None:
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-gateway-admin"), credentials=NoCredentials())
    async with app.router.lifespan_context(app):
        gateway: PhoneGateway = app.state.phone_gateway
        assert gateway.status()["listening"] is False
        for address in ["0.0.0.0", "127.0.0.1", "8.8.8.8", "localhost", "https://example.com"]:
            with pytest.raises(ValueError):
                await gateway.start(address)
        await gateway.start("127.0.0.1", allow_loopback=True)
        port = gateway.status()["port"]
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert (await client.get("/api/v2/settings")).status_code == 404
            assert (await client.post("/phone/v1", json={})).status_code == 400
            assert (await client.post("/phone/v1", json={}, headers={"Origin": "https://evil.example"})).status_code == 403
            assert (await client.post("/phone/v1", json={}, headers={"Host": "evil.example"})).status_code == 403
            assert (await client.post("/phone/v1", content=b"x" * (1024 * 1024 + 1), headers={"Content-Type": "application/json"})).status_code == 413
        await gateway.close()
        assert gateway.status()["listening"] is False
        async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
            with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
                await client.get(f"http://127.0.0.1:{port}/phone/v1")


async def test_admin_pairing_routes_require_desktop_identity(tmp_path: Path) -> None:
    app = create_app(RuntimeConfig(data_dir=tmp_path, api_token="synthetic-gateway-admin"), credentials=NoCredentials())
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        assert (await client.get("/api/v2/phone")).status_code == 401
        response = await client.get("/api/v2/phone", headers={"Authorization": "Bearer synthetic-gateway-admin"})
        assert response.status_code == 200
        assert response.json() == {"listening": False, "address": None, "port": None, "connections": []}
        assert "secret" not in json.dumps(response.json())
