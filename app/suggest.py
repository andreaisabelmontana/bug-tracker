"""Assignee suggestion from resolved-bug history.

We build one document per assignee by concatenating the title+description of
every bug they have resolved (status ``closed``). A TF-IDF vectorizer is fit
over those per-assignee documents, and a new bug is scored against each assignee
by cosine similarity of its TF-IDF vector to theirs. The assignee whose past
resolved work is most similar to the new bug is suggested.

This is purely history-driven: with no resolved bugs there is nothing to learn
from, so we return no suggestion rather than guessing.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class AssigneeSuggester:
    """Cosine-similarity ranking of assignees by their resolved-bug corpus."""

    def __init__(self, resolved_bugs: list[dict]):
        # Group resolved-bug text by assignee.
        corpus: dict[str, list[str]] = defaultdict(list)
        for bug in resolved_bugs:
            who = bug.get("assignee")
            if not who:
                continue
            corpus[who].append(f"{bug.get('title', '')} {bug.get('description', '')}")

        self.assignees: list[str] = sorted(corpus)
        self._fitted = len(self.assignees) > 0
        if not self._fitted:
            return

        documents = [" ".join(corpus[a]) for a in self.assignees]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
        )
        self.matrix = self.vectorizer.fit_transform(documents)

    def rank(self, title: str, description: str = "") -> list[tuple[str, float]]:
        """All assignees ranked by similarity to the new bug (desc order)."""
        if not self._fitted:
            return []
        query = self.vectorizer.transform([f"{title} {description}".strip()])
        sims = cosine_similarity(query, self.matrix)[0]
        ranked = sorted(
            zip(self.assignees, (float(s) for s in sims)),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return ranked

    def suggest(self, title: str, description: str = "") -> Optional[dict]:
        """Best assignee plus the full ranked scoreboard, or ``None`` if no history."""
        ranked = self.rank(title, description)
        if not ranked or ranked[0][1] <= 0.0:
            return None
        best, score = ranked[0]
        return {
            "assignee": best,
            "score": round(score, 4),
            "ranking": [{"assignee": a, "score": round(s, 4)} for a, s in ranked],
        }


def suggest_assignee(resolved_bugs: list[dict], title: str, description: str = "") -> Optional[dict]:
    """Convenience one-shot: build a suggester from history and query it."""
    return AssigneeSuggester(resolved_bugs).suggest(title, description)
