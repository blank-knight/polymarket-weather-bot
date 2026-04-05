# Polymarket Weather Trading Bot

Automated trading bot for Polymarket weather prediction markets.

## Strategy

Exploits the time lag between professional weather model updates (GFS/ECMWF/UKMO/NWS) and Polymarket weather market prices. When models update every 6 hours, the bot detects pricing discrepancies and generates trading signals.

**Edge = Multi-model fusion consensus vs. market price**

## Architecture

```
Open-Meteo API (GFS/ECMWF/UKMO/NWS)
        ↓
   Probability Engine (multi-model blend, Bayesian fusion)
        ↓
   Polymarket Gamma API → Market Discovery
   Polymarket CLOB API → Price Query
        ↓
   Signal Generator (Edge → Kelly → TradeSignal)
        ↓
   Risk Manager (7 safety checks)
        ↓
   Trade Executor (simulation / live)
```

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your wallet keys

# Run
python main.py --once       # Single scan
python main.py --scheduler  # 24/7 scheduled
python main.py --summary    # Trading summary
```

## Configuration

Key parameters in `src/config/settings.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| MIN_EDGE | 0.05 | Minimum edge to trade |
| KELLY_FRACTION | 0.25 | Quarter-Kelly sizing |
| MAX_POSITION_RATIO | 0.15 | Max 15% bankroll per trade |
| INITIAL_BANKROLL | 100 | Starting bankroll (USD) |

## Cities

26 cities across 4 priority levels:
- **P0**: New York, London, Chicago
- **P1**: Paris, LA, Miami, Dallas, Atlanta, Seattle, Toronto, São Paulo, Buenos Aires
- **P2**: Seoul, Tokyo, Sydney, Hong Kong, Singapore, Shanghai, Beijing
- **P3**: Austin, Denver, Houston, San Francisco, Mexico City, Moscow, Istanbul

## Tech Stack

- Python 3.12 + asyncio
- Open-Meteo API (free weather data)
- Polymarket Gamma API + CLOB API
- SQLite (trades/signals/forecasts storage)
- APScheduler (6h trading cycle)

## License

MIT
