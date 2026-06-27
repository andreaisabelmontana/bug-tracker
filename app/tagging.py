"""Auto-tagging: assign labels to a bug from its title + description.

A small, transparent classifier. We train a TF-IDF vectorizer plus a
one-vs-rest Logistic Regression on a hand-written seed set (``seed_labels.json``),
one binary classifier per label. Because it is multi-label, a bug can receive
several tags: every label whose predicted probability clears a threshold is
attached, and the top label is always kept so we never return nothing.

The model is explainable: ``explain_label`` surfaces the highest-weighted
vocabulary terms the classifier learned for any label, and ``top_terms`` shows
which terms in a given bug drove each predicted label.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

LABELS = ["crash", "ui", "performance", "auth", "database", "network"]

_SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_labels.json")


def _load_seed() -> tuple[list[str], list[list[str]]]:
    with open(_SEED_PATH, encoding="utf-8") as fh:
        rows = json.load(fh)
    texts = [r["text"] for r in rows]
    labels = [[r["label"]] for r in rows]
    return texts, labels


class AutoTagger:
    """TF-IDF + one-vs-rest Logistic Regression multi-label tagger."""

    def __init__(self, threshold: float = 0.30):
        self.threshold = threshold
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            stop_words="english",
        )
        self.binarizer = MultiLabelBinarizer(classes=LABELS)
        self.clf = OneVsRestClassifier(
            LogisticRegression(max_iter=1000, C=8.0, class_weight="balanced")
        )
        self._fit()

    def _fit(self) -> None:
        texts, labels = _load_seed()
        x = self.vectorizer.fit_transform(texts)
        y = self.binarizer.fit_transform(labels)
        self.clf.fit(x, y)

    # ----- prediction ------------------------------------------------------------

    def scores(self, title: str, description: str = "") -> dict[str, float]:
        """Per-label probability for a bug's combined text."""
        text = f"{title} {description}".strip()
        x = self.vectorizer.transform([text])
        probs = self.clf.predict_proba(x)[0]
        return {label: float(p) for label, p in zip(self.binarizer.classes_, probs)}

    def tag(self, title: str, description: str = "") -> list[str]:
        """Return the labels for a bug, highest-confidence first.

        Every label over ``threshold`` is included; if none clears it, the single
        best label is returned so the bug is never left untagged.
        """
        scores = self.scores(title, description)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        chosen = [label for label, p in ranked if p >= self.threshold]
        if not chosen:
            chosen = [ranked[0][0]]
        return chosen

    # ----- explainability --------------------------------------------------------

    def explain_label(self, label: str, k: int = 8) -> list[tuple[str, float]]:
        """Top-weighted vocabulary terms the model learned for ``label``."""
        idx = list(self.binarizer.classes_).index(label)
        coefs = self.clf.estimators_[idx].coef_[0]
        vocab = np.array(self.vectorizer.get_feature_names_out())
        order = np.argsort(coefs)[::-1][:k]
        return [(vocab[i], float(coefs[i])) for i in order]

    def top_terms(self, title: str, description: str = "", k: int = 5) -> dict[str, list[str]]:
        """For each predicted label, the terms in this bug that drove it."""
        text = f"{title} {description}".strip()
        x = self.vectorizer.transform([text])
        present = x.nonzero()[1]
        vocab = self.vectorizer.get_feature_names_out()
        out: dict[str, list[str]] = {}
        for label in self.tag(title, description):
            idx = list(self.binarizer.classes_).index(label)
            coefs = self.clf.estimators_[idx].coef_[0]
            contrib = sorted(
                ((vocab[i], coefs[i] * x[0, i]) for i in present),
                key=lambda kv: kv[1],
                reverse=True,
            )
            out[label] = [term for term, c in contrib[:k] if c > 0]
        return out


@lru_cache(maxsize=1)
def get_tagger() -> AutoTagger:
    """Process-wide singleton; training is cheap but only needs to happen once."""
    return AutoTagger()
