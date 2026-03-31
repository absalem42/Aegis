# Product v0

## Project Goal

Build Aegis as a local, solo-operator trading agent demo that is fast to iterate on during a hackathon. The project should emphasize clarity, small moving parts, and a credible path to later exchange and trust-layer integrations without implementing those integrations yet.

## One-Sentence Product Description

Aegis is a local paper-trading agent with a Streamlit dashboard, SQLite storage, and future-ready seams for exchange and trust artifact integrations.

## v0 Demo Objective

Deliver a local paper-trading demo for a single operator, not a live trading system.

## Primary Operator Workflow

1. Run the app locally.
2. Inspect the dashboard.
3. Review positions, trades, daily metrics, and artifacts.
4. Reset or reseed local demo data when needed.

## In Scope

- Python as the main implementation language
- Streamlit dashboard for local interaction
- SQLite persistence
- Paper trading only
- Local recording of simple trust/proof artifact records
- Local evaluation reports and a transparent internal scorecard
- Readable, hackathon-friendly structure for one primary operator

## Out of Scope

- Live trading
- Real Kraken execution
- On-chain publication
- Multi-user authentication or role management
- Background automation, schedulers, or workers
- Production-grade infrastructure concerns

## Local Success Criteria

v0 is successful when all of the following are true:

- The app runs locally.
- Demo data can be created, reset, or reseeded locally.
- Paper trades and positions persist in SQLite.
- The dashboard clearly exposes the current local state.
- Local evaluations can be run and compared safely.
- The project remains understandable and easy to extend during the hackathon.

## Boundary Reminder

v0 is a local paper-trading demo. It is not a live trading system and should not be described or implemented as one.
