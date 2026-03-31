# Data Model

## SQLite-First Approach

Aegis v0 is SQLite-first.

- Use one local SQLite database file.
- Keep the schema simple and readable.
- Direct SQL is acceptable for v0.
- Optimize for hackathon speed and clarity, not for heavy abstraction.

## Planned Minimum Tables

### `trades`

Purpose: store executed fills only.

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
- `artifact_id`
- `order_id`
- `execution_provider`

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

These are useful when the audit trail needs to distinguish order lifecycle from fills:

- `signals`
- `agent_runs`
- `orders`
- `portfolio_snapshots`

### `orders`

Purpose: store local order-lifecycle records separately from fills.

Suggested columns:

- `id`
- `ts`
- `run_id`
- `symbol`
- `side`
- `quantity`
- `order_type`
- `artifact_id`
- `execution_provider`
- `execution_mode`
- `status`
- `external_order_id`
- `response_json`
- `notes`

If added, the table should stay lightweight and make the audit trail clearer rather than introducing a full broker backend abstraction.

## Core Invariants

- Paper trading only.
- Positions reflect executed trades only.
- Orders represent intent and provider response metadata; fills still live in `trades`.
- Blocked trades do not mutate positions.
- Artifacts are append-friendly local audit material.
- Daily metrics should be derivable from recorded local trading activity.

## Reset and Seed Expectations

- Local development should support resetting demo data safely.
- Seeding should produce predictable demo states for testing and demos.
- Reset and seed behavior should be explicit and easy to understand.
- Local evaluation reports may be stored as JSON files under `reports/` rather than new SQLite tables.

## Migration Policy

- During v0, manual and simple schema evolution is acceptable.
- Avoid migration frameworks during hackathon development.
- If the schema changes, update this document promptly so the docs remain accurate.
