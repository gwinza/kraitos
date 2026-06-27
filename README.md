# Kraitos

A modular forex trading bot platform built in Python. Kraitos separates concerns across broker connectivity, strategy logic, risk management, execution, backtesting, and analytics so each component can evolve independently.

## Project Structure

```
kraitos/
├── broker/          # Broker API adapters and connection management
├── config/          # Configuration files and settings loaders
├── data/            # Market data ingestion, storage, and feeds
├── strategies/      # Trading strategy definitions and signals
├── risk/            # Position sizing, exposure limits, and safeguards
├── execution/       # Order routing and trade lifecycle management
├── backtesting/     # Historical simulation and performance replay
├── analytics/       # Metrics, reporting, and performance analysis
├── dashboard/       # Monitoring UI and operational views
├── logs/            # Runtime log output (gitignored)
├── tests/           # Unit and integration tests
├── main.py          # Application entry point
├── requirements.txt # Python dependencies
└── .env.example     # Environment variable template
```

## Requirements

- Python 3.11+
- pip

## Quick Start

1. **Clone and enter the project**

   ```bash
   cd kraitos
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux / macOS
   .venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**

   ```bash
   cp .env.example .env
   # Edit .env with your broker credentials and settings
   ```

5. **Review configuration**

   Edit `config/config.yaml` to match your trading environment (symbols, timeframes, risk limits).

6. **Run the application**

   ```bash
   python main.py
   ```

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Secrets and environment-specific overrides (not committed) |
| `config/config.yaml` | Application settings, modules, and defaults |

## Development

```bash
# Run tests
pytest

# Format code
black .

# Lint
ruff check .
```

## Status

This repository contains the initial project skeleton. Trading logic, broker integrations, and strategy implementations are not yet included.

## License

Proprietary — all rights reserved.
