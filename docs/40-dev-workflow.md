# Development Workflow

## Python Version

The baseline assumption for Aegis v0 is Python `3.12.x`.

## Local Setup

Use local development as the default path for Aegis.

Typical setup steps:

1. Inspect the repository.
2. Inspect git status.
3. Create a virtual environment.
4. Activate the virtual environment.
5. Install dependencies.

Example commands:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

These commands are the intended workflow once the corresponding project files exist.

## Standard Run Commands

```powershell
streamlit run app.py
```

Use the dashboard controls to run local evaluations and save reports under `reports/`.

## Standard Test Commands

```powershell
pytest -q
ruff check .
```

## Lint and Style Expectations

- Keep modules readable.
- Prefer small functions with clear responsibilities.
- Use type hints where they add clarity.
- Keep the dependency footprint minimal.
- Avoid clever abstractions that make solo maintenance harder.

## Codex Task Workflow

Before changing code, Codex should mentally check this list:

- Inspect the repo.
- Inspect git status.
- Read `AGENTS.md`.
- Read the relevant docs file.
- Scope edits narrowly.

During implementation:

- Change only what is necessary for the task.
- Verify the touched behavior.
- Keep docs and implementation aligned.

## What Not to Do

- Do not add Docker.
- Do not add CI setup.
- Do not add ORM tooling.
- Do not add migration tooling.
- Do not add schedulers or worker systems.
- Do not add live trading support in v0.
- Do not introduce speculative abstractions beyond the documented future boundaries.

## Definition of Done

A task is done when:

- The request is satisfied.
- Code and docs are aligned.
- Relevant checks are run or any gaps are explicitly reported.
- The git state remains safe and understandable.

## Local vs New Worktree vs Cloud

- Local: use for the main implementation flow.
- New worktree: use for risky parallel experiments or feature spikes that should not disturb the main local flow.
- Cloud: use for isolated review, audit, or cleanup tasks where separation is helpful.
