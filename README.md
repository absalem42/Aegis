# Aegis

Aegis is a solo-hackathon Python trading agent project. v0 is a local Streamlit and SQLite paper-trading scaffold with deterministic demo data, real Kraken public market-data support through REST or the official Kraken CLI, paper-only execution, local evaluation scorecards, and future-ready seams for ERC-8004-style trust workflows.

## v0 Scope

- Streamlit dashboard
- SQLite persistence
- Paper trading only
- Deterministic local market data for BTC/USD, ETH/USD, and SOL/USD
- Local trade-intent artifact generation before execution

v0 does not support live trading.

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

The app includes local-only controls to run one engine cycle, reset runtime state, and reseed a predictable demo state.
It also exposes explicit market-data and execution modes. The safe default is `mock` market data plus `paper` execution.
`kraken + paper` uses real public Kraken market data when available, while all execution remains local paper execution.
Kraken market data can run through the built-in REST adapter or an optional official Kraken CLI backend.
Kraken execution is still a stub and does not enable live trading or authenticated exchange access.
The dashboard also shows local agent identity and trust/validation readiness for proof artifacts; ERC-8004 publishing remains deferred.
The app can also run a local evaluation, save JSON reports under `reports/`, and show a transparent local score. That score is internal to Aegis and is not the official hackathon leaderboard.

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
- Kraken execution remains a stub/readiness boundary only.
- Local evaluation reports and a transparent internal score are supported.
- Local trust/readiness structure exists for proof artifacts.
- ERC-8004 support is a stub/readiness boundary only.
