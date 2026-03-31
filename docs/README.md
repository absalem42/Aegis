# Aegis Docs

## Purpose

This `docs/` folder is the canonical, durable documentation set for Aegis. It defines the intended v0 product boundaries, architecture shape, data model, development workflow, and future integration direction for the project.

## Reading Order

1. [10-product-v0.md](10-product-v0.md)
2. [20-architecture-v0.md](20-architecture-v0.md)
3. [30-data-model.md](30-data-model.md)
4. [40-dev-workflow.md](40-dev-workflow.md)
5. [50-future-integrations.md](50-future-integrations.md)

## Source-of-Truth Precedence

Use this order when there is any ambiguity:

1. Current repository reality and checked-in code
2. Files in `docs/`
3. `AGENTS.md` as a short operational map

If code and docs drift, treat that as a documentation defect to fix quickly.

## Current Project Status

- The repository is being scaffolded.
- v0 is a local paper-trading demo only.
- Kraken public market data is supported.
- Kraken execution is future-facing only.
- ERC-8004 trust/proof support is future-facing only.
- The near-term priority is a simple, readable, solo-hackathon-friendly codebase.

## Sync Rule

Docs must stay in sync with implementation. Update the relevant docs file whenever implementation meaningfully changes behavior, boundaries, storage, or workflow.
