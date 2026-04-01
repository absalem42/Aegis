# Aegis

Aegis is a solo-hackathon Python trading agent project. v0 is a local Streamlit and SQLite trading scaffold with deterministic demo data, real Kraken public market-data support through REST or the official Kraken CLI, internal paper execution by default, guarded Kraken CLI execution paths, local evaluation scorecards, and future-ready seams for ERC-8004-style trust workflows.

## v0 Scope

- Streamlit dashboard
- SQLite persistence
- Paper trading only
- Deterministic local market data for BTC/USD, ETH/USD, and SOL/USD
- Local trade-intent artifact generation before execution

v0 does not support unattended live trading. Any Kraken live submit path is disabled by default, manual single-cycle only, and heavily gated.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The `.env` file is optional for v0 because safe local defaults are built in.

## Run

```powershell
streamlit run app.py
```

The app includes local-only controls to run one engine cycle, reset runtime state, reseed a predictable demo state, and run local evaluations.
It also exposes explicit market-data and execution modes. The safe default is `mock` market data plus internal `paper` execution.
Market data can come from mock, Kraken public REST, or an optional official Kraken CLI backend.
Execution can run through the internal paper engine or the Kraken CLI paper suite, while SQLite remains the local audit and evaluation source of truth.
Kraken live execution now supports guarded Kraken CLI auth + validate preflight and an optional real market submit path, but only for manual single-cycle use after every live gate passes. It is disabled by default and records submitted-vs-preflight-only states honestly.
The dashboard also shows local agent identity and trust/validation readiness for proof artifacts; ERC-8004 publishing remains deferred.
The app can run local evaluations, save JSON reports under `reports/`, and show a transparent local score. That score is internal to Aegis and is not the official hackathon leaderboard. Evaluations remain internal-paper-only even if the app is configured for Kraken execution.

## Test

```powershell
pytest -q
```

## Lint

```powershell
ruff check .
```

## Notes

- v0 is paper trading only.
- Default mode is mock market data plus paper execution.
- Kraken public market data is supported.
- Kraken CLI market-data alignment is supported as an optional backend.
- Kraken CLI paper execution is supported as a simulation path.
- Kraken live execution remains guarded and disabled by default.
- Aegis can run Kraken CLI `auth test`, `order ... --validate`, and an optional real `kraken order buy|sell <PAIR> <VOL> --type market -o json` submit path only for manual single-cycle use.
- Aegis does not fake fills when the immediate live response is partial; it records fill-unknown states honestly.
- Local evaluation reports and a transparent internal score are supported.
- Local trust/readiness structure exists for proof artifacts.
- ERC-8004 support is a stub/readiness boundary only.
