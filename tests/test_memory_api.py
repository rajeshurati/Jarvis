"""User-editable memory API tests."""

from fastapi.testclient import TestClient

from jarvis.api.app import create_app
from jarvis.application.assistant_service import AssistantService
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.language import LanguageMessage
from jarvis.core.config import Settings


class Model:
    def complete(self, messages: list[LanguageMessage]) -> str:
        return "ok"


class Automation:
    def try_execute(self, command: str) -> ActionResult | None:
        return None


def test_memory_crud_and_projects(test_settings: Settings) -> None:
    app = create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
    )
    with TestClient(app) as client:
        saved = client.put(
            "/memory",
            json={"category": "preference", "key": "editor", "value": "VS Code"},
        )
        assert saved.status_code == 200
        memory_id = saved.json()["id"]
        assert client.get("/memory").json()[0]["value"] == "VS Code"

        project = client.post(
            "/projects",
            json={"name": "Jarvis", "objective": "Build local AI"},
        )
        assert project.status_code == 201
        project_id = project.json()["id"]
        task = client.post(f"/projects/{project_id}/tasks", json={"title": "Test memory"})
        assert task.status_code == 201
        assert client.get(f"/projects/{project_id}/tasks").json()[0]["title"] == "Test memory"
        assert client.get("/projects").json()[0]["name"] == "Jarvis"

        assert client.delete(f"/memory/{memory_id}").status_code == 204
        assert client.delete(f"/memory/{memory_id}").status_code == 404


def test_missing_project_task_returns_not_found(test_settings: Settings) -> None:
    app = create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
    )
    with TestClient(app) as client:
        response = client.post("/projects/999/tasks", json={"title": "Impossible"})
    assert response.status_code == 404


def test_reminder_api_creates_lists_and_claims_due_items(test_settings: Settings) -> None:
    app = create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
    )
    with TestClient(app) as client:
        created = client.post(
            "/reminders",
            json={"title": "Wake up", "due_at": "2020-01-01T08:00:00-05:00"},
        )
        assert created.status_code == 201
        assert client.get("/reminders").json()[0]["title"] == "Wake up"
        claimed = client.post("/reminders/claim-due")
        assert claimed.status_code == 200
        assert claimed.json()[0]["status"] == "delivered"
        assert client.post("/reminders/claim-due").json() == []


def test_reminder_api_requires_timezone(test_settings: Settings) -> None:
    app = create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/reminders",
            json={"title": "Invalid", "due_at": "2026-08-01T08:00:00"},
        )
    assert response.status_code == 422


def test_audit_api_is_read_only_and_bounded(test_settings: Settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        client.post("/assistant/respond", json={"text": "what time is it"})
        response = client.get("/audit", params={"limit": 2})
        assert response.status_code == 200
        assert len(response.json()) == 2
        assert client.post("/audit", json={}).status_code == 405
        assert client.get("/audit", params={"limit": 0}).status_code == 422


def test_workflow_api_creates_and_exposes_ordered_steps(test_settings: Settings) -> None:
    app = create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
    )
    with TestClient(app) as client:
        created = client.post(
            "/workflows",
            json={"name": "Morning", "commands": ["open Gmail", "tell me the time"]},
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]
        assert client.get("/workflows").json()[0]["status"] == "ready"
        steps = client.get(f"/workflows/{workflow_id}/steps").json()
        assert [step["position"] for step in steps] == [0, 1]
        assert client.get("/workflows/999/steps").status_code == 404
