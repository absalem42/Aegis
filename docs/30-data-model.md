# Data Model

## SQLite-First Approach

Aegis v0 is SQLite-first.

- Use one local SQLite database file.
- Keep the schema simple and readable.
- Direct SQL is acceptable for v0.
- Optimize for hackathon speed and clarity, not for heavy abstraction.

## Planned Minimum Tables

### `trades`

Purpose: store executed paper trades.

Minimum recommended columns:

- `id`
- `ts`
- `symbol`
- `side`
- `quantity`
- `price`
- `notional`
- `reason`
- `status`

### `blocked_trades`

Purpose: record trade attempts that were intentionally blocked.

Minimum recommended columns:

- `id`
- `ts`
- `symbol`
- `side`
- `attempted_quantity`
- `attempted_price`
- `block_reason`
- `context_json`

### `positions`

Purpose: track the current paper position state by symbol.

Minimum recommended columns:

- `symbol`
- `quantity`
- `average_cost`
- `last_price`
- `market_value`
- `unrealized_pnl`
- `updated_at`

### `artifacts`

Purpose: store local trust/proof artifact records for audit and future export.

Minimum recommended columns:

- `id`
- `ts`
- `artifact_type`
- `subject`
- `payload_json`
- `hash_or_digest`
- `notes`

### `daily_metrics`

Purpose: store per-day summary metrics for the local trading demo.

Minimum recommended columns:

- `trading_day`
- `starting_cash`
- `ending_cash`
- `realized_pnl`
- `unrealized_pnl`
- `trade_count`
- `blocked_trade_count`

## Optional or Future-Facing Tables

These are not required for the first pass, but may become useful later:

- `signals`
- `agent_runs`
- `orders`
- `portfolio_snapshots`

If added later, they should remain clearly justified and not complicate the minimum v0 schema.

## Core Invariants

- Paper trading only.
- Positions reflect executed trades only.
- Blocked trades do not mutate positions.
- Artifacts are append-friendly local audit material.
- Daily metrics should be derivable from recorded local trading activity.

## Reset and Seed Expectations

- Local development should support resetting demo data safely.
- Seeding should produce predictable demo states for testing and demos.
- Reset and seed behavior should be explicit and easy to understand.

## Migration Policy

- During v0, manual and simple schema evolution is acceptable.
- Avoid migration frameworks during hackathon development.
- If the schema changes, update this document promptly so the docs remain accurate.
