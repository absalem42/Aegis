# Future Integrations

## Intent

This file describes how Aegis should stay ready for future integrations without turning them into v0 work.

## Kraken Integration Shape Later

Kraken should appear as adapters behind the existing boundaries, not as logic mixed directly into the core engine.

Expected shape:

- A market-data-facing adapter for public Kraken data
- A broker-facing adapter for execution behavior later
- Authentication and request signing isolated inside the adapter layer
- Minimal Kraken-specific leakage into core trading logic

Current reality:

- Public Kraken market data may be used in v0 through a direct REST adapter or an optional Kraken CLI-backed read-only path.
- Kraken CLI paper execution may be used in v0 as a simulation path that mirrors outcomes back into local SQLite.
- Kraken live execution remains guarded, disabled by default, and intended only for manual single-cycle use.
- The current live-facing boundary supports `kraken auth test`, `kraken order ... --validate`, and a tightly gated real market submit path when all live gates pass.
- Local receipts and order records must still distinguish blocked, preflight-only, submitted-fill-unknown, and submitted-with-fill states honestly.

## ERC-8004 / Trust Artifact Shape Later

ERC-8004-related work should later build on local artifact generation rather than replacing it.

Expected shape:

- Local artifacts remain the source material in v0.
- A separate export or publish layer can later transform those artifacts for external proof workflows.
- Publishing or verification logic should remain isolated from the core trading path.

## Allowed Placeholders and Stubs in v0

The following are acceptable in v0:

- Interface definitions
- Clearly marked stub classes or functions
- Placeholder modules that establish clean future seams
- Read-only Kraken CLI alignment for public market data
- Kraken CLI paper-execution alignment that stays clearly non-live

The following are not acceptable in v0:

- Fake live trading flows
- Simulated exchange auth that looks production-ready
- Claims that external trust publication already exists

## Explicitly Deferred

- Broad or unattended real exchange execution
- Authenticated Kraken flows beyond guarded `auth test`, validate, and single-order spot submit
- Broad CLI account mutation flows beyond the guarded single-order spot submit path
- Secret management for unattended live trading
- On-chain publishing or verification
- Production trust, dispute, or attestation workflows
- Operational hardening for external integrations

## Clean Upgrade Path After v0

1. Stabilize the local paper-trading flow.
2. Introduce clear adapter stubs where needed.
3. Add integration-oriented tests around those boundaries.
4. Add real external integrations only after the local core is stable and the interfaces are holding up.
