"""Assignee suggestion: a clearly-matching bug routes to the historical expert."""
import pytest

from app.models import Database
from app.seed import seed_database
from app.suggest import AssigneeSuggester, suggest_assignee


@pytest.fixture(scope="module")
def suggester():
    db = Database(":memory:")
    seed_database(db)
    return AssigneeSuggester(db.resolved_bugs())


@pytest.mark.parametrize(
    "title,description,expected",
    [
        # Each maps to the assignee who resolved that category in seed_bugs.json.
        ("App crashed with a segfault and core dump",
         "fatal exception and null pointer on startup", "ada"),       # crash -> ada
        ("Button is misaligned and the css layout is broken",
         "dark mode contrast is wrong on mobile", "beck"),            # ui -> beck
        ("The dashboard is painfully slow",
         "high latency, slow query, terrible p99 performance", "cruz"),  # performance -> cruz
        ("Login fails with a valid password",
         "oauth token rejected, auth session expires", "devi"),       # auth -> devi
        ("Database connection pool is exhausted",
         "sql query times out, the db is unreachable", "evan"),       # database -> evan
        ("Requests time out behind the proxy",
         "connection refused, dns fails, tcp packets dropped", "faye"),  # network -> faye
    ],
)
def test_suggests_historical_expert(suggester, title, description, expected):
    result = suggester.suggest(title, description)
    assert result is not None
    assert result["assignee"] == expected
    # The winner must strictly out-score the runner-up.
    ranking = result["ranking"]
    assert ranking[0]["score"] > ranking[1]["score"]


def test_no_history_returns_none():
    assert suggest_assignee([], "anything", "at all") is None


def test_ranking_covers_all_assignees(suggester):
    result = suggester.suggest("crash on startup", "fatal segfault")
    assert {r["assignee"] for r in result["ranking"]} == set(suggester.assignees)
