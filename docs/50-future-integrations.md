# Future Integrations

## Intent

This file describes how Aegis should stay ready for future integrations without turning them into v0 work.

## Kraken Integration Shape Later

Kraken should later appear as an adapter behind the existing boundaries, not as logic mixed directly into the core engine.

Expected shape:

- A broker-facing adapter for execution behavior
- A market-data-facing adapter if Kraken market data is used
- Authentication and request signing isolated inside the adapter layer
- Minimal Kraken-specific leakage into core trading logic

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

The following are not acceptable in v0:

- Fake live trading flows
- Simulated exchange auth that looks production-ready
- Claims that external trust publication already exists

## Explicitly Deferred

- Real exchange execution
- Secret management for live trading
- On-chain publishing or verification
- Production trust, dispute, or attestation workflows
- Operational hardening for external integrations

## Clean Upgrade Path After v0

1. Stabilize the local paper-trading flow.
2. Introduce clear adapter stubs where needed.
3. Add integration-oriented tests around those boundaries.
4. Add real external integrations only after the local core is stable and the interfaces are holding up.
