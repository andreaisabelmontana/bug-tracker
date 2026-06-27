"""Auto-tagging behaviour: bugs get sensible labels from their text."""
import pytest

from app.tagging import LABELS, get_tagger


@pytest.fixture(scope="module")
def tagger():
    return get_tagger()


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("App crashes with a fatal exception on launch",
         "Segfault and core dump at startup, null pointer in init", "crash"),
        ("Dashboard is extremely slow to load",
         "High latency, the query takes several seconds, p99 is terrible", "performance"),
        ("Cannot log in with the correct password",
         "OAuth token rejected and the auth session expires", "auth"),
        ("Dropdown menu renders off screen",
         "CSS layout breaks and the modal is not centered, bad styling", "ui"),
        ("Database connection pool exhausted",
         "SQL queries fail with a pool timeout, the db is unreachable", "database"),
        ("Requests time out behind the proxy",
         "Connection refused, socket reset and TCP packets dropped", "network"),
    ],
)
def test_top_label_is_correct(tagger, title, description, expected):
    labels = tagger.tag(title, description)
    # The expected label must be present and it must be the highest-scoring one.
    assert expected in labels
    scores = tagger.scores(title, description)
    top = max(scores, key=scores.get)
    assert top == expected


def test_tag_never_empty(tagger):
    labels = tagger.tag("something vague happened", "no clear keywords here at all")
    assert len(labels) >= 1


def test_all_labels_are_known(tagger):
    labels = tagger.tag("the database query is slow and the page crashed", "")
    assert set(labels).issubset(set(LABELS))


def test_explainability_terms(tagger):
    # The learned vocabulary for 'crash' should include crash-ish terms.
    terms = [t for t, _ in tagger.explain_label("crash", k=10)]
    assert any(k in " ".join(terms) for k in ("crash", "segfault", "fatal", "exception"))


def test_top_terms_explains_prediction(tagger):
    evidence = tagger.top_terms("the page is very slow and laggy", "high latency")
    assert "performance" in evidence
    assert evidence["performance"]  # non-empty list of driving terms
