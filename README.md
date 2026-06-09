# Bug Tracker — Interactive Showcase

An interactive static showcase for a comprehensive **issue-tracking system** with both a web UI and a
CLI, featuring **automated tag generation** from issue content and **intelligent assignee suggestions**
based on expertise and workload.

🔗 **Live site:** https://andreaisabelmontana.github.io/bug-tracker/

## What it does
- **Dual interface** — modern web UI + a full Typer CLI for automation/scripting.
- **Projects & issues** — full CRUD with filtering and search over issues and tags.
- **Automatic tags** — case-insensitive, word-boundary keyword matching across title/description/logs (bug · frontend · backend · performance).
- **Smart assignee** — ranks teammates by success rate (closed issues per tag), tie-broken by lowest workload; focuses on high-priority open issues.
- **Analytics & observability** — usage charts, health checks, Prometheus metrics.

**Stack:** FastAPI · Typer (CLI) · SQLite · Docker + Azure Container Instances · Prometheus · pytest (coverage gate) · CI/CD.

## About this repo
An original, hand-built static site (single `index.html`, no framework) presenting the project, with a
scripted interactive triage demo that reproduces the real keyword + workload logic on sample team data.
Built from scratch.
