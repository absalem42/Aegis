# Aegis

Aegis is a solo-hackathon Python trading agent project. v0 is a local Streamlit and SQLite paper-trading scaffold with future-ready seams for Kraken and ERC-8004 integrations.

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
It also exposes explicit market-data and execution modes. The safe default is `mock` market data plus `paper` execution; Kraken-related modes are readiness stubs only and do not enable live trading.

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
- Kraken support is a stub/readiness boundary only.
- ERC-8004 support is a stub only.
