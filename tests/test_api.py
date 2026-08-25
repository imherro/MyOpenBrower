from fastapi.testclient import TestClient

from gateway.api import create_app
from gateway.config import Settings


def test_create_and_fetch_task(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False))
    with TestClient(app) as client:
        created = client.post("/api/chat", json={"session_id": "general", "prompt": "hello"})
        assert created.status_code == 202
        payload = created.json()
        assert payload["status"] == "pending"
        fetched = client.get(f"/api/tasks/{payload['task_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["session_id"] == "general"
        assert fetched.json()["prompt"] == "hello"
        assert fetched.json()["answer"] is None
        listed = client.get("/api/tasks")
        assert listed.status_code == 200
        assert [task["task_id"] for task in listed.json()] == [payload["task_id"]]


def test_test_console_is_served(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False))
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "测试控制台" in response.text
    assert "/api/tasks" in response.text


def test_session_and_memory_api(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False))
    with TestClient(app) as client:
        created = client.post("/api/sessions", json={"session_id": "investing", "profile_name": "finance"})
        assert created.status_code == 201
        assert created.json()["profile_name"] == "finance"
        memory = client.post("/api/sessions/investing/memory", json={"content": "风险偏好保守"})
        assert memory.status_code == 201
        assert client.get("/api/sessions/investing/memory").json()[0]["content"] == "风险偏好保守"
        disabled = client.patch("/api/sessions/investing", json={"enabled": False})
        assert disabled.json()["enabled"] is False


def test_api_key_is_enforced_when_configured(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False, api_key="test-key"))
    with TestClient(app) as client:
        assert client.get("/api/tasks").status_code == 401
        assert client.get("/api/tasks", headers={"X-API-Key": "test-key"}).status_code == 200


def test_cancel_and_retry_task(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False))
    with TestClient(app) as client:
        task_id = client.post("/api/chat", json={"session_id": "general", "prompt": "hello"}).json()["task_id"]
        cancelled = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        retried = client.post(f"/api/tasks/{task_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["status"] == "pending"


def test_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("GATEWAY_HOST", "127.0.0.1")
    monkeypatch.setenv("GATEWAY_PORT", "12345")
    settings = Settings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.port == 12345


def test_invalid_session_is_rejected(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "gateway.db", worker_enabled=False))
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"session_id": "not valid", "prompt": "hello"})
    assert response.status_code == 422


def test_demo_worker_completes_task(tmp_path):
    app = create_app(Settings(
        db_path=tmp_path / "gateway.db",
        worker_enabled=True,
        provider="demo",
        poll_interval_seconds=0.01,
    ))
    with TestClient(app) as client:
        created = client.post("/api/chat", json={"session_id": "general", "prompt": "hello"}).json()
        for _ in range(50):
            fetched = client.get(f"/api/tasks/{created['task_id']}").json()
            if fetched["status"] == "completed":
                break
        assert fetched["status"] == "completed"
        assert fetched["answer"] == "[demo:general] hello"
