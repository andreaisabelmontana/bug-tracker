# Bug Tracker

A FastAPI service and a CLI for tracking bugs, backed by SQLite, with two real
algorithms doing the triage:

- **Auto-tagging** — labels a bug from its title + description using a TF-IDF +
  Logistic Regression multi-label classifier trained on a seed set.
- **Assignee suggestion** — ranks past assignees by TF-IDF cosine similarity of
  the new bug to each assignee's corpus of previously-resolved bugs.

🔗 **Showcase site:** https://andreaisabelmontana.github.io/bug-tracker/
(static demo UI — the backend below is the real Python implementation.)

## The algorithms

### Auto-tagging (`app/tagging.py`)
The label set is `crash · ui · performance · auth · database · network`.

A `TfidfVectorizer` (uni- and bi-grams, English stop-words, sublinear TF) feeds a
one-vs-rest `LogisticRegression` — one binary classifier per label — trained on
`app/seed_labels.json` (48 hand-labelled example phrases). It is multi-label:
every label whose predicted probability clears a threshold (`0.30`) is attached,
and the single best label is always kept so a bug is never left untagged.

It is explainable. `explain_label(label)` returns the highest-weighted vocabulary
terms the model learned for a label; `top_terms(title, description)` shows which
terms in a *specific* bug drove each predicted label (coefficient × TF-IDF weight).

```
crash        crashes, exception, process, crash, fatal, app
ui           layout, screen, broken, wrong, invisible
performance  slow, latency, takes, load, endpoint
auth         password, invalid, token, fails, authorization
database     database, db, table, sql, query
network      connection, network, host, proxy, request
```

### Assignee suggestion (`app/suggest.py`)
We build one document per assignee by concatenating every bug they have
**resolved** (`status = closed`). A TF-IDF model is fit over those per-assignee
documents and a new bug is scored against each by **cosine similarity**. The
assignee whose past resolved work is most similar is suggested. With no resolved
history there is nothing to learn from, so no suggestion is returned (rather than
guessing).

The seed history (`app/seed_bugs.json`, 24 resolved bugs across 6 people) gives
each person a clear specialty: `ada→crash, beck→ui, cruz→performance,
devi→auth, evan→database, faye→network`.

## Example output

`python demo.py` (real run, no server started):

```
>> App crashes with a fatal exception on launch
    tags       : crash
    evidence   : crash <- crashes, exception, fatal, core, core dump
    assignee   : ada  (cosine 0.4226)
    scoreboard : ada=0.4226, cruz=0.0127, beck=0.0, devi=0.0, evan=0.0, faye=0.0

>> Checkout page is extremely slow to load
    tags       : performance
    evidence   : performance <- slow, latency, takes, load, p99
    assignee   : cruz  (cosine 0.4057)
    scoreboard : cruz=0.4057, evan=0.0444, beck=0.0155, faye=0.0114, ada=0.0, devi=0.0

>> Database connection pool keeps getting exhausted
    tags       : database
    evidence   : database <- database, db, pool, sql, db unreachable
    assignee   : evan  (cosine 0.435)
    scoreboard : evan=0.435, faye=0.0676, ada=0.0, beck=0.0, cruz=0.0, devi=0.0
```

## API

Run the server:

```bash
pip install -r requirements.txt
uvicorn app.api:app --reload
# interactive docs at http://127.0.0.1:8000/docs
```

| Method | Route                  | Purpose                                            |
|--------|------------------------|----------------------------------------------------|
| GET    | `/health`              | liveness + bug count                               |
| GET    | `/labels`              | the label vocabulary                               |
| POST   | `/tag`                 | auto-tag a title/description (scores + evidence)   |
| POST   | `/suggest`             | suggest an assignee from history (no write)        |
| POST   | `/bugs`                | create a bug — auto-tags + suggests assignee       |
| GET    | `/bugs`                | list bugs (`?status=&assignee=&label=`)            |
| GET    | `/bugs/{id}`           | one bug with its comments                          |
| PATCH  | `/bugs/{id}`           | update title/description/assignee/labels/status    |
| POST   | `/bugs/{id}/status`    | change status (`open`/`in-progress`/`closed`)      |
| POST   | `/bugs/{id}/comments`  | add a comment                                      |
| DELETE | `/bugs/{id}`           | delete a bug                                        |

On create, a bug is auto-tagged (unless `labels` are supplied) and, if no
`assignee` is given, the history-based suggestion is filled in. The DB is seeded
with the historical bugs on first start, so suggestions work out of the box.

```bash
curl -X POST localhost:8000/bugs -H 'content-type: application/json' \
  -d '{"title":"Login fails with valid password","description":"oauth token rejected, auth session expires"}'
# -> {"id":25,"labels":["auth"],"assignee":"devi", ...}
```

## CLI

Same database, same algorithms (`python -m app.cli ...`):

```bash
python -m app.cli seed                          # load historical bugs
python -m app.cli add "Login fails" -d "oauth token rejected"   # auto-tag + suggest
python -m app.cli list --status open
python -m app.cli show 1
python -m app.cli status 1 in-progress
python -m app.cli assign 1 ada
python -m app.cli comment 1 "looking into it" --author ada
python -m app.cli tag "Dashboard is very slow to load"          # no write
python -m app.cli suggest "Database deadlock on writes"         # no write
```

DB path defaults to `./bugtracker.db`; override with `--db PATH` or `BUGTRACKER_DB`.

## Project layout

```
app/
  models.py        SQLite data layer (bugs + comments)
  tagging.py       TF-IDF + LogisticRegression auto-tagger
  suggest.py       TF-IDF cosine assignee suggester
  api.py           FastAPI app (create_app factory + `app` instance)
  cli.py           argparse CLI
  seed.py          load seed bugs into a Database
  seed_bugs.json   24 historical resolved bugs
  seed_labels.json 48 labelled phrases the tagger trains on
tests/             pytest suite (TestClient + algorithm tests)
demo.py            seed + print real tag/suggestion examples
```

## Tests

```bash
python -m pytest -q
```

```
.................................                                        [100%]
33 passed in 0.80s
```

The suite asserts auto-tags are sensible, that a clearly-matching bug is routed
to the historically-correct assignee, and that CRUD + status transitions +
comments all work through the FastAPI `TestClient`.

## License

MIT — see [LICENSE](LICENSE).
