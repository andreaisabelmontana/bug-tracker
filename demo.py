"""Runnable demo: seed an in-memory DB and print real auto-tag + suggestion output.

Run with:  python demo.py

Starts no server. It seeds an in-memory database with the historical bugs, then
exercises the auto-tagger and the assignee suggester directly, and finally drives
the FastAPI app through its TestClient to show the create -> tag -> assign flow.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import create_app
from app.models import Database
from app.seed import seed_database
from app.suggest import AssigneeSuggester
from app.tagging import get_tagger

LINE = "-" * 68

NEW_BUGS = [
    ("App crashes with a fatal exception on launch",
     "Segfault and core dump immediately at startup, null pointer in init."),
    ("Checkout page is extremely slow to load",
     "High latency, the query takes several seconds and p99 is terrible."),
    ("Cannot log in with the right password",
     "OAuth token is rejected and the auth session expires immediately."),
    ("Dropdown menu renders off screen on mobile",
     "The CSS layout breaks and the modal is not centered, bad styling."),
    ("Database connection pool keeps getting exhausted",
     "SQL queries fail with a pool timeout, the db becomes unreachable."),
    ("Requests time out behind the proxy",
     "Connection refused, the socket resets and TCP packets are dropped."),
]


def main() -> None:
    db = Database(":memory:")
    n = seed_database(db)
    tagger = get_tagger()
    suggester = AssigneeSuggester(db.resolved_bugs())

    print(LINE)
    print(f"Seeded {n} historical resolved bugs across "
          f"{len(suggester.assignees)} assignees: {', '.join(suggester.assignees)}")
    print(LINE)
    print("AUTO-TAGGING  +  ASSIGNEE SUGGESTION  (direct function calls)")
    print(LINE)

    for title, desc in NEW_BUGS:
        labels = tagger.tag(title, desc)
        evidence = tagger.top_terms(title, desc)
        suggestion = suggester.suggest(title, desc)
        print(f"\n>> {title}")
        print(f"    tags       : {', '.join(labels)}")
        ev = "; ".join(f"{lbl} <- {', '.join(terms)}" for lbl, terms in evidence.items() if terms)
        if ev:
            print(f"    evidence   : {ev}")
        if suggestion:
            board = ", ".join(f"{r['assignee']}={r['score']}" for r in suggestion["ranking"])
            print(f"    assignee   : {suggestion['assignee']}  (cosine {suggestion['score']})")
            print(f"    scoreboard : {board}")

    print("\n" + LINE)
    print("WHAT THE MODEL LEARNED  (top terms per label)")
    print(LINE)
    for label in tagger.binarizer.classes_:
        terms = ", ".join(t for t, _ in tagger.explain_label(label, k=6))
        print(f"  {label:<12} {terms}")

    print("\n" + LINE)
    print("FULL API FLOW via FastAPI TestClient")
    print(LINE)
    app = create_app(db_path=":memory:", seed=True)
    client = TestClient(app)

    resp = client.post("/bugs", json={
        "title": "Login fails after the latest deploy",
        "description": "Users get an invalid token error and the OAuth sign in loop never completes.",
    })
    bug = resp.json()
    print(f"  POST /bugs -> {resp.status_code}")
    print(f"    id={bug['id']} status={bug['status']} labels={bug['labels']} assignee={bug['assignee']}")

    client.post(f"/bugs/{bug['id']}/status", json={"status": "in-progress"})
    client.post(f"/bugs/{bug['id']}/comments", json={"body": "Reproduced, fixing the refresh path", "author": "devi"})
    final = client.post(f"/bugs/{bug['id']}/status", json={"status": "closed"}).json()
    detail = client.get(f"/bugs/{bug['id']}").json()
    print(f"    open -> in-progress -> closed; final status={final['status']}, "
          f"{len(detail['comments'])} comment(s)")
    print(LINE)


if __name__ == "__main__":
    main()
