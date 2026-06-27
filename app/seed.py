"""Load the historical seed bugs into a Database so suggestions work out of the box."""
from __future__ import annotations

import json
import os

from .models import Database

_SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_bugs.json")


def load_seed_bugs() -> list[dict]:
    with open(_SEED_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def seed_database(db: Database) -> int:
    """Insert all seed bugs into ``db``. Returns the number inserted."""
    count = 0
    for bug in load_seed_bugs():
        db.create_bug(
            title=bug["title"],
            description=bug.get("description", ""),
            assignee=bug.get("assignee"),
            labels=bug.get("labels", []),
            status=bug.get("status", "closed"),
        )
        count += 1
    return count
