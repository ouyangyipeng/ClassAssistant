from httpx import AsyncClient


async def test_health_works_without_a_model_key_and_exposes_no_paths(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "2.0.1"}


async def test_credentials_required_for_settings_and_classroom_data(client: AsyncClient) -> None:
    for path in ["/api/v2/settings", "/api/v2/sessions", "/api/settings"]:
        response = await client.get(path, headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 401


async def test_untrusted_browser_origin_cannot_use_even_a_valid_token(client: AsyncClient) -> None:
    response = await client.get("/api/v2/settings", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403


async def test_text_session_stop_and_restart_preserve_history(client: AsyncClient) -> None:
    response = await client.post("/api/v2/sessions", json={"course_name": "操作系统", "source": "text"})
    assert response.status_code == 201
    session_id = response.json()["id"]
    response = await client.post(f"/api/v2/sessions/{session_id}/entries", json={"text": "进程与线程共享不同的资源。", "source_id": "test-1"})
    assert response.status_code == 201
    assert (await client.post(f"/api/v2/sessions/{session_id}/stop")).status_code == 200
    assert (await client.post("/api/v2/sessions", json={"course_name": "计算机网络", "source": "text"})).status_code == 201
    entries = (await client.get(f"/api/v2/sessions/{session_id}/entries")).json()
    assert [entry["text"] for entry in entries] == ["进程与线程共享不同的资源。"]
    assert len((await client.get("/api/v2/sessions")).json()) == 2
    exported = await client.get(f"/api/v2/sessions/{session_id}/export")
    assert exported.status_code == 200
    assert "进程与线程共享不同的资源。" in exported.text


async def test_second_active_classroom_is_rejected_without_changing_first(client: AsyncClient) -> None:
    first = (await client.post("/api/v2/sessions", json={"course_name": "第一课", "source": "text"})).json()
    assert (await client.post("/api/v2/sessions", json={"course_name": "第二课", "source": "text"})).status_code == 409
    assert (await client.get("/api/v2/status")).json()["session"]["id"] == first["id"]


async def test_pause_rejects_audio_text_until_resume(client: AsyncClient) -> None:
    session = (await client.post("/api/v2/sessions", json={"source": "text"})).json()
    path = f"/api/v2/sessions/{session['id']}"
    assert (await client.post(f"{path}/pause")).status_code == 200
    assert (await client.post(f"{path}/entries", json={"text": "不应记录", "source_id": "p1"})).status_code == 409
    assert (await client.post(f"{path}/resume")).status_code == 200
    assert (await client.post(f"{path}/entries", json={"text": "恢复记录", "source_id": "p2"})).status_code == 201


async def test_settings_validate_and_take_effect_without_restart(client: AsyncClient) -> None:
    preferences = (await client.get("/api/v2/settings")).json()
    preferences["keywords"] = ["欧同学"]
    assert (await client.put("/api/v2/settings", json=preferences)).status_code == 200
    assert (await client.get("/api/v2/settings")).json()["keywords"] == ["欧同学"]
    preferences["llm"]["api_key"] = "synthetic-test-key"
    assert (await client.put("/api/v2/settings", json=preferences)).status_code == 422


async def test_missing_material_does_not_start_or_change_session(client: AsyncClient) -> None:
    response = await client.post("/api/v2/sessions", json={"source": "text", "material_id": "../outside.txt"})
    assert response.status_code == 404
    assert (await client.get("/api/v2/status")).json()["session"] is None


async def test_upload_is_stored_as_an_id_and_invalid_files_leave_no_materials(client: AsyncClient) -> None:
    bad = await client.post("/api/v2/materials", files={"file": ("corrupt.docx", b"not-office", "application/octet-stream")})
    assert bad.status_code == 422
    assert (await client.get("/api/v2/materials")).json() == []
    first = await client.post("/api/v2/materials", files={"file": ("lesson.txt", "操作系统讲义".encode(), "text/plain")})
    second = await client.post("/api/v2/materials", files={"file": ("lesson.txt", "网络讲义".encode(), "text/plain")})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert len((await client.get("/api/v2/materials")).json()) == 2
    created = await client.post("/api/v2/sessions", json={"source": "text", "material_id": first.json()["id"]})
    assert created.status_code == 201


async def test_large_body_is_rejected_before_parsing(client: AsyncClient) -> None:
    response = await client.post("/api/v2/materials", content=b"tiny", headers={"Content-Length": str(100 * 1024 * 1024)})
    assert response.status_code == 413


async def test_unrecognized_endpoint_does_not_return_html_or_traceback(client: AsyncClient) -> None:
    response = await client.get("/api/v2/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


async def test_non_ascii_invalid_bearer_is_rejected_without_server_error(client: AsyncClient) -> None:
    response = await client.get("/api/v2/settings", headers=[(b"Authorization", b"Bearer \xff")])
    assert response.status_code == 401
