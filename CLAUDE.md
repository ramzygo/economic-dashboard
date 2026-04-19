# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app (opens at http://localhost:8501)
streamlit run app.py

# Offline development (uses sample data, no API keys needed)
ECONOMIC_DASHBOARD_OFFLINE=true streamlit run app.py

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_data_loader.py -v

# Run with coverage
python -m pytest tests/ --cov=modules --cov=pages

# Initialize DuckDB schema
python scripts/init_database.py

# Set up API keys interactively
python scripts/setup_credentials.py

# Refresh data manually
python scripts/refresh_data.py
```

## Architecture

This is a **Streamlit multi-page app** (`app.py` + `pages/`). Pages are auto-discovered by Streamlit via numeric prefixes in filenames (e.g., `1_GDP_and_Growth.py`).

### Data Flow

1. Pages call `modules/data_loader.py` for FRED/Yahoo Finance/World Bank data
2. `data_loader.py` checks a 24-hour pickle cache in `data/cache/` before hitting external APIs
3. If `ECONOMIC_DASHBOARD_OFFLINE=true`, falls back to CSV sample data in `data/`
4. DuckDB (`data/duckdb/economic_dashboard.duckdb`) provides persistent storage for ML features and predictions — accessed via `modules/database/`

### Module Organization

- **`modules/data_loader.py`** — primary data fetching with caching and rate limiting; FRED series IDs are registered in `modules/data_series_config.py`
- **`modules/database/`** — DuckDB backend: `connection.py` (singleton), `schema.py` (table defs), `queries.py` (1100+ line query module)
- **`modules/auth/credentials_manager.py`** — Fernet-encrypted API key storage; keys live in `data/credentials/` (gitignored)
- **`modules/features/`** — feature engineering pipeline: technical indicators, options metrics, margin risk scoring, financial health, sector rotation, insider trading
- **`modules/ml/`** — XGBoost/LightGBM models for recession probability and stock prediction; trained models persisted to disk

### Config

- **`config_settings.py`** — reads env vars for offline mode, cache TTL, rate limits
- **`.streamlit/config.toml`** — dark theme and server settings

### API Keys

Stored encrypted via `credentials_manager.py`. Supported services: FRED, Yahoo Finance, Alpha Vantage, Quandl, World Bank. Without keys, the app uses cached/sample data. The `6_API_Key_Management.py` page provides a UI for managing keys at runtime.

### Branching

CI/CD uses `dev` and `main` branches. PRs go to `dev`; `promote-dev-to-prod.yml` workflow handles promotion to `main`.
