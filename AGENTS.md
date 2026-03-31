# Aegis Agents Guide

## Project Summary

Aegis is a solo-hackathon Python trading agent project. v0 is a local paper-trading demo with a Streamlit dashboard and SQLite storage. Kraken and ERC-8004 support are future-facing only and should appear as interfaces or stubs later, not as live integrations in v0.

## Read This First

- Start with [docs/README.md](docs/README.md).
- Then read the docs file that matches the area you are changing.

## Non-Negotiable v0 Rules

- Paper trading only.
- SQLite only.
- Keep modules simple and readable.
- Prefer the Python standard library and simple libraries over heavy frameworks.

## Git Safety Rules

- Do not switch branches.
- Do not rebase.
- Do not merge.
- Do not reset.
- Do not commit unless explicitly requested.
- Stop and inspect before editing if the repo state looks unusual.

## Quick Run/Test Placeholders

- Python environment setup: `python -m venv .venv`
- Activate environment (PowerShell): `.\.venv\Scripts\Activate.ps1`
- Install dependencies: `pip install -r requirements.txt`
- Run app: `streamlit run app.py`
- Run tests: `pytest -q`
- Run lint: `ruff check .`

## Nested AGENTS.md Policy

- Do not add nested `AGENTS.md` files yet.
- Add nested agent files later only if a subtree genuinely needs special rules.
