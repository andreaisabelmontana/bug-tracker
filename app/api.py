"""FastAPI service for the bug tracker.

Routes
------
GET    /health                      liveness probe
GET    /labels                      the label vocabulary
POST   /tag                         auto-tag arbitrary title/description (no write)
POST   /suggest                     suggest an assignee from history (no write)
POST   /bugs                        create a bug (auto-tags + suggests assignee)
GET    /bugs                        list bugs (filter by status/assignee/label)
GET    /bugs/{id}                   fetch one bug with its comments
PATCH  /bugs/{id}                   update title/description/assignee/labels/status
POST   /bugs/{id}/status            change status (open/in-progress/closed)
POST   /bugs/{id}/comments          add a comment
DELETE /bugs/{id}                   delete a bug

On create, the service auto-tags the bug (unless labels are supplied) and, if no
assignee is given, fills in the history-based suggestion.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .models import STATUSES, Database
from .seed import seed_database
from .suggest import AssigneeSuggester
from .tagging import get_tagger

# ----- request / response schemas ------------------------------------------------


class BugCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    assignee: Optional[str] = None
    labels: Optional[list[str]] = None
    status: str = "open"
    auto_tag: bool = True
    auto_assign: bool = True


class BugUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee: Optional[str] = None
    labels: Optional[list[str]] = None
    status: Optional[str] = None


class StatusChange(BaseModel):
    status: str


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1)
    author: str = "anonymous"


class TagRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""


# ----- app factory ---------------------------------------------------------------


def create_app(db_path: Optional[str] = None, seed: bool = True) -> FastAPI:
    app = FastAPI(title="Bug Tracker", version="1.0.0")
    db = Database(db_path or os.environ.get("BUGTRACKER_DB", ":memory:"))
    if seed and not db.list_bugs():
        seed_database(db)
    app.state.db = db

    def suggester() -> AssigneeSuggester:
        return AssigneeSuggester(db.resolved_bugs())

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "bugs": len(db.list_bugs())}

    @app.get("/labels")
    def labels() -> dict:
        return {"labels": get_tagger().binarizer.classes_.tolist()}

    @app.post("/tag")
    def tag(req: TagRequest) -> dict:
        tagger = get_tagger()
        return {
            "labels": tagger.tag(req.title, req.description),
            "scores": {k: round(v, 4) for k, v in tagger.scores(req.title, req.description).items()},
            "evidence": tagger.top_terms(req.title, req.description),
        }

    @app.post("/suggest")
    def suggest(req: TagRequest) -> dict:
        result = suggester().suggest(req.title, req.description)
        return {"suggestion": result}

    @app.post("/bugs", status_code=201)
    def create_bug(payload: BugCreate) -> dict:
        if payload.status not in STATUSES:
            raise HTTPException(422, f"invalid status; expected one of {STATUSES}")

        labels = payload.labels
        if labels is None and payload.auto_tag:
            labels = get_tagger().tag(payload.title, payload.description)

        assignee = payload.assignee
        suggestion = None
        if assignee is None and payload.auto_assign:
            suggestion = suggester().suggest(payload.title, payload.description)
            if suggestion:
                assignee = suggestion["assignee"]

        bug = db.create_bug(
            title=payload.title,
            description=payload.description,
            assignee=assignee,
            labels=labels,
            status=payload.status,
        )
        bug["suggestion"] = suggestion
        return bug

    @app.get("/bugs")
    def list_bugs(
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        label: Optional[str] = None,
    ) -> dict:
        return {"bugs": db.list_bugs(status=status, assignee=assignee, label=label)}

    @app.get("/bugs/{bug_id}")
    def get_bug(bug_id: int) -> dict:
        bug = db.get_bug(bug_id)
        if bug is None:
            raise HTTPException(404, "bug not found")
        return bug

    @app.patch("/bugs/{bug_id}")
    def update_bug(bug_id: int, payload: BugUpdate) -> dict:
        try:
            bug = db.update_bug(bug_id, **payload.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if bug is None:
            raise HTTPException(404, "bug not found")
        return bug

    @app.post("/bugs/{bug_id}/status")
    def change_status(bug_id: int, payload: StatusChange) -> dict:
        try:
            bug = db.set_status(bug_id, payload.status)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if bug is None:
            raise HTTPException(404, "bug not found")
        return bug

    @app.post("/bugs/{bug_id}/comments", status_code=201)
    def add_comment(bug_id: int, payload: CommentCreate) -> dict:
        comment = db.add_comment(bug_id, payload.body, payload.author)
        if comment is None:
            raise HTTPException(404, "bug not found")
        return comment

    @app.delete("/bugs/{bug_id}", status_code=204)
    def delete_bug(bug_id: int) -> None:
        if not db.delete_bug(bug_id):
            raise HTTPException(404, "bug not found")

    return app


# Default app instance for ``uvicorn app.api:app``.
app = create_app()
