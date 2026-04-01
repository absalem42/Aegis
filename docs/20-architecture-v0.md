# Architecture v0

## Design Principles

- Keep the code simple, readable, and solo-hackathon friendly.
- Prefer small modules with clear responsibilities.
- Keep dependencies minimal.
- Introduce explicit interfaces only where later integrations are expected.
- Avoid architectural patterns that add ceremony without immediate value.

## Proposed High-Level Layout

The project will likely grow into a structure similar to this:

```text
app.py
aegis/
  config.py
  db.py
  engine.py
  market_data.py
  broker.py
  artifacts.py
  portfolio.py
  strategy.py
  integrations/
    kraken.py
  trust/
    erc8004.py
tests/
```

This is a target layout, not a statement that the repository already contains these files.

## Control Flow

The intended v0 control flow is:

`Streamlit -> engine -> broker -> DB`

In practice:

- Streamlit collects operator intent and displays current state.
- The engine applies simple trading logic and coordination.
- The broker layer handles paper execution decisions.
- SQLite stores durable local state.
- A local evaluation/reporting layer may run multiple engine cycles, read the resulting state, and save JSON reports without changing the core trading path.

## Market Data Interface Boundary

- Keep a clear boundary around market price input.
- v0 may use deterministic local data or lightweight public price inputs.
- A real Kraken public REST market-data adapter is acceptable in v0 as long as execution remains local and paper-only.
- An optional Kraken CLI-backed public market-data adapter is also acceptable when it stays read-only and paper execution remains the only live execution path.
- Do not couple the core engine directly to authenticated exchange APIs.
- The market data boundary should make it possible to introduce Kraken-facing or other providers later without rewriting the engine.

## Broker Interface Boundary

- Treat order execution as an interface boundary.
- v0 now has two safe simulation paths:
  - internal paper execution
  - Kraken CLI paper execution
- Execution logic should be isolated from Streamlit UI code.
- Kraken-specific behavior belongs in an adapter, not in the core engine.
- Kraken live execution remains a guarded readiness path in this milestone.
- The only live-facing behavior currently allowed is Kraken CLI auth plus `order ... --validate` preflight. No live submit occurs.
- A minimal local order lifecycle may be stored separately from fills so audit views can distinguish intents, orders, receipts, and trades.

## Trust Artifact Interface Boundary

- Treat trust/proof artifact generation and persistence as their own boundary.
- v0 should support local artifact creation and storage only.
- External proof publishing or verification should remain deferred.
- ERC-8004-facing work should later plug into this boundary instead of leaking into unrelated modules.

## Extension Points for Later

- Kraken public market data can already plug into the market data boundary through REST or an optional official CLI backend.
- Kraken CLI paper execution can already plug into the broker boundary as a simulation path.
- Kraken live execution still belongs in a later guarded adapter flow behind the broker boundary.
- ERC-8004 can later plug into artifact export or publishing paths.
- These extension points should stay explicit but lightweight in v0.

## Non-Goals and Anti-Patterns

- No ORM
- No migrations framework
- No service split or microservice layout
- No scheduler or worker framework
- No premature plugin system
- No exchange-specific logic scattered through the core flow
- No over-abstracted architecture before there is working local paper-trading behavior
