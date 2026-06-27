"""Command-line interface for the bug tracker.

Backed by the same SQLite database and the same auto-tag / suggest algorithms as
the API. Uses only the standard library (argparse) so it runs anywhere.

Examples
--------
    python -m app.cli seed
    python -m app.cli add "Login fails with valid password" -d "OAuth token rejected"
    python -m app.cli list
    python -m app.cli list --status open
    python -m app.cli show 1
    python -m app.cli status 1 in-progress
    python -m app.cli comment 1 "Looking into it" --author ada
    python -m app.cli tag "Dashboard is very slow to load"
    python -m app.cli suggest "Database connection pool exhausted"

The database file defaults to ``bugtracker.db`` in the repo root; override with
``--db PATH`` or the ``BUGTRACKER_DB`` environment variable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .models import STATUSES, Database
from .seed import seed_database
from .suggest import AssigneeSuggester
from .tagging import get_tagger


def _db(args) -> Database:
    path = args.db or os.environ.get("BUGTRACKER_DB") or os.path.join(
        os.path.dirname(__file__), "..", "bugtracker.db"
    )
    return Database(path)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _fmt_bug(bug: dict) -> str:
    labels = ", ".join(bug["labels"]) or "-"
    who = bug["assignee"] or "unassigned"
    return f"#{bug['id']:<3} [{bug['status']:<11}] {bug['title']}  ({labels}) -> {who}"


# ----- command handlers ----------------------------------------------------------


def cmd_seed(args) -> int:
    db = _db(args)
    n = seed_database(db)
    print(f"Seeded {n} historical bugs into {db.path}")
    return 0


def cmd_add(args) -> int:
    db = _db(args)
    labels = args.labels
    if labels is None:
        labels = get_tagger().tag(args.title, args.description)
    assignee = args.assignee
    suggestion = None
    if assignee is None:
        suggestion = AssigneeSuggester(db.resolved_bugs()).suggest(args.title, args.description)
        if suggestion:
            assignee = suggestion["assignee"]
    bug = db.create_bug(
        title=args.title,
        description=args.description,
        assignee=assignee,
        labels=labels,
        status=args.status,
    )
    print(_fmt_bug(bug))
    print(f"  auto-tags : {', '.join(bug['labels'])}")
    if suggestion:
        ranking = " | ".join(f"{r['assignee']}={r['score']}" for r in suggestion["ranking"][:4])
        print(f"  suggested : {suggestion['assignee']} (score {suggestion['score']}) [{ranking}]")
    return 0


def cmd_list(args) -> int:
    db = _db(args)
    bugs = db.list_bugs(status=args.status, assignee=args.assignee, label=args.label)
    if not bugs:
        print("No bugs match.")
        return 0
    for bug in bugs:
        print(_fmt_bug(bug))
    return 0


def cmd_show(args) -> int:
    db = _db(args)
    bug = db.get_bug(args.id)
    if bug is None:
        print(f"Bug #{args.id} not found", file=sys.stderr)
        return 1
    _print(bug)
    return 0


def cmd_status(args) -> int:
    db = _db(args)
    if args.status not in STATUSES:
        print(f"Invalid status; expected one of {STATUSES}", file=sys.stderr)
        return 2
    bug = db.set_status(args.id, args.status)
    if bug is None:
        print(f"Bug #{args.id} not found", file=sys.stderr)
        return 1
    print(_fmt_bug(bug))
    return 0


def cmd_assign(args) -> int:
    db = _db(args)
    bug = db.update_bug(args.id, assignee=args.assignee)
    if bug is None:
        print(f"Bug #{args.id} not found", file=sys.stderr)
        return 1
    print(_fmt_bug(bug))
    return 0


def cmd_comment(args) -> int:
    db = _db(args)
    comment = db.add_comment(args.id, args.body, args.author)
    if comment is None:
        print(f"Bug #{args.id} not found", file=sys.stderr)
        return 1
    print(f"Comment #{comment['id']} added to bug #{args.id} by {comment['author']}")
    return 0


def cmd_tag(args) -> int:
    tagger = get_tagger()
    labels = tagger.tag(args.title, args.description)
    scores = tagger.scores(args.title, args.description)
    print(f"labels: {', '.join(labels)}")
    for label in labels:
        terms = tagger.top_terms(args.title, args.description).get(label, [])
        print(f"  {label:<12} p={scores[label]:.3f}  because: {', '.join(terms) or '-'}")
    return 0


def cmd_suggest(args) -> int:
    db = _db(args)
    result = AssigneeSuggester(db.resolved_bugs()).suggest(args.title, args.description)
    if result is None:
        print("No suggestion (no resolved-bug history). Run `seed` first.")
        return 0
    print(f"suggested: {result['assignee']} (score {result['score']})")
    for r in result["ranking"]:
        print(f"  {r['assignee']:<8} {r['score']}")
    return 0


# ----- parser --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bug-tracker", description="Bug tracker CLI")
    p.add_argument("--db", help="SQLite database path (default: ./bugtracker.db)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("seed", help="load historical seed bugs")
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("add", help="create a bug (auto-tags + suggests assignee)")
    sp.add_argument("title")
    sp.add_argument("-d", "--description", default="")
    sp.add_argument("-a", "--assignee", default=None)
    sp.add_argument("-l", "--labels", nargs="*", default=None)
    sp.add_argument("-s", "--status", default="open", choices=STATUSES)
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="list bugs")
    sp.add_argument("--status", choices=STATUSES, default=None)
    sp.add_argument("--assignee", default=None)
    sp.add_argument("--label", default=None)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="show one bug with comments")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("status", help="change a bug's status")
    sp.add_argument("id", type=int)
    sp.add_argument("status", choices=STATUSES)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("assign", help="set a bug's assignee")
    sp.add_argument("id", type=int)
    sp.add_argument("assignee")
    sp.set_defaults(func=cmd_assign)

    sp = sub.add_parser("comment", help="add a comment to a bug")
    sp.add_argument("id", type=int)
    sp.add_argument("body")
    sp.add_argument("--author", default="anonymous")
    sp.set_defaults(func=cmd_comment)

    sp = sub.add_parser("tag", help="auto-tag a title/description (no write)")
    sp.add_argument("title")
    sp.add_argument("-d", "--description", default="")
    sp.set_defaults(func=cmd_tag)

    sp = sub.add_parser("suggest", help="suggest an assignee from history (no write)")
    sp.add_argument("title")
    sp.add_argument("-d", "--description", default="")
    sp.set_defaults(func=cmd_suggest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
