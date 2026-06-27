"""End-to-end API tests via FastAPI's TestClient: CRUD, status, comments, auto-fill."""
import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["bugs"] >= 24  # seed data present


def test_labels_endpoint(client):
    r = client.get("/labels")
    assert r.status_code == 200
    assert set(r.json()["labels"]) == {"crash", "ui", "performance", "auth", "database", "network"}


def test_create_bug_auto_tags_and_assigns(client):
    r = client.post("/bugs", json={
        "title": "App crashes on startup with a segfault",
        "description": "fatal exception, core dump, null pointer in init",
    })
    assert r.status_code == 201
    bug = r.json()
    assert "crash" in bug["labels"]          # sensible auto-tag
    assert bug["assignee"] == "ada"          # historical crash expert
    assert bug["suggestion"]["assignee"] == "ada"
    assert bug["status"] == "open"


def test_create_bug_auth_routes_to_devi(client):
    r = client.post("/bugs", json={
        "title": "Login fails with the correct password",
        "description": "oauth token rejected and the auth session expires too early",
    })
    bug = r.json()
    assert "auth" in bug["labels"]
    assert bug["assignee"] == "devi"


def test_explicit_labels_and_assignee_respected(client):
    r = client.post("/bugs", json={
        "title": "Custom issue",
        "description": "no auto anything",
        "labels": ["network"],
        "assignee": "zoe",
    })
    bug = r.json()
    assert bug["labels"] == ["network"]
    assert bug["assignee"] == "zoe"
    assert bug["suggestion"] is None


def test_get_and_list_and_filter(client):
    created = client.post("/bugs", json={
        "title": "Slow dashboard", "description": "high latency slow query"
    }).json()
    # get one
    got = client.get(f"/bugs/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]
    # list all
    all_bugs = client.get("/bugs").json()["bugs"]
    assert any(b["id"] == created["id"] for b in all_bugs)
    # filter by status
    open_bugs = client.get("/bugs", params={"status": "open"}).json()["bugs"]
    assert all(b["status"] == "open" for b in open_bugs)
    # filter by label
    perf = client.get("/bugs", params={"label": "performance"}).json()["bugs"]
    assert all("performance" in b["labels"] for b in perf)


def test_get_missing_bug_404(client):
    assert client.get("/bugs/999999").status_code == 404


def test_status_transitions(client):
    bug = client.post("/bugs", json={"title": "Transition me", "description": "x"}).json()
    bid = bug["id"]
    for state in ("in-progress", "closed", "open"):
        r = client.post(f"/bugs/{bid}/status", json={"status": state})
        assert r.status_code == 200
        assert r.json()["status"] == state


def test_invalid_status_rejected(client):
    bug = client.post("/bugs", json={"title": "X", "description": "y"}).json()
    r = client.post(f"/bugs/{bug['id']}/status", json={"status": "banana"})
    assert r.status_code == 422


def test_update_bug(client):
    bug = client.post("/bugs", json={"title": "Old title", "description": "z"}).json()
    r = client.patch(f"/bugs/{bug['id']}", json={"title": "New title", "assignee": "ada"})
    assert r.status_code == 200
    assert r.json()["title"] == "New title"
    assert r.json()["assignee"] == "ada"


def test_comments(client):
    bug = client.post("/bugs", json={"title": "Commentable", "description": "z"}).json()
    r = client.post(f"/bugs/{bug['id']}/comments", json={"body": "first!", "author": "beck"})
    assert r.status_code == 201
    assert r.json()["author"] == "beck"
    detail = client.get(f"/bugs/{bug['id']}").json()
    assert len(detail["comments"]) == 1
    assert detail["comments"][0]["body"] == "first!"


def test_comment_on_missing_bug_404(client):
    assert client.post("/bugs/999999/comments", json={"body": "hi"}).status_code == 404


def test_delete_bug(client):
    bug = client.post("/bugs", json={"title": "Delete me", "description": "z"}).json()
    assert client.delete(f"/bugs/{bug['id']}").status_code == 204
    assert client.get(f"/bugs/{bug['id']}").status_code == 404


def test_tag_endpoint(client):
    r = client.post("/tag", json={"title": "the database query is very slow", "description": ""})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["labels"], list) and body["labels"]
    assert set(body["scores"]) == {"crash", "ui", "performance", "auth", "database", "network"}


def test_suggest_endpoint(client):
    r = client.post("/suggest", json={
        "title": "Database deadlock on concurrent writes",
        "description": "sql transaction rolls back, the db locks up",
    })
    assert r.status_code == 200
    assert r.json()["suggestion"]["assignee"] == "evan"
