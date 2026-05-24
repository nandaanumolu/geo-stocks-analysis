# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in API key before first run
cp .env.example .env

# Run the Streamlit app
streamlit run src/ui/app.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_analysis_agent.py -v

# Run a single test
pytest tests/test_backtest_agent.py::TestComputeMetrics::test_perfect_hit_rate_when_all_correct -v
```

## Architecture

The system is a multi-agent pipeline: **News → Analysis → Recommendations → Backtest**.

```
src/
├── agents/          # Orchestration agents (call each other in sequence)
│   ├── news_agent.py           # Entry point: fetches news from GDELT or RSS
│   ├── analysis_agent.py       # Calls Claude API, returns GeoAnalysis (Pydantic)
│   ├── recommendation_agent.py # Maps sector signals to stocks from india_stocks.json
│   └── backtest_agent.py       # Runs full pipeline for a past date + computes returns
├── data/
│   ├── gdelt_client.py         # GDELT 2.0 Doc API — historical news by date + country
│   ├── stock_client.py         # yfinance wrapper — NSE prices (.NS suffix), Nifty 50
│   └── db.py                   # SQLAlchemy models (SQLite); call init_db() before use
├── models/                     # Pydantic v2 data contracts shared across agents
│   ├── events.py               # NewsItem, GeoEvent, GeoAnalysis
│   ├── recommendations.py      # StockRecommendation
│   └── backtest.py             # BacktestStock, BacktestResult, PerformanceMetrics
├── config/
│   ├── india_stocks.json       # ~52 NSE stocks with sector + geo_sensitivity tags
│   ├── sector_signals.json     # Static event-type → sector impact mapping
│   └── settings.py             # Pydantic BaseSettings; loads ANTHROPIC_API_KEY from .env
└── ui/app.py                   # Streamlit app — 3 tabs: Live, Backtest, History
```

## Key Design Decisions

**Claude integration** (`analysis_agent.py`): The system prompt is marked `cache_control: ephemeral` for Anthropic prompt caching. Claude receives up to 30 news article titles and must return valid JSON matching the `GeoAnalysis` schema. If JSON parsing fails, a single retry is attempted.

**Stock universe** (`india_stocks.json`): Each stock has a `geo_sensitivity` list (event type strings). The recommendation engine scores sectors via `_resolve_sector_signals()` — multiplying event confidence × magnitude weight — then maps positive/negative scores to BUY/SELL signals. Stocks with confidence below 40% are filtered out.

**GDELT limitations**: The free GDELT Doc API reliably covers the last ~3 months; older dates may return sparse results. Results are cached in SQLite (`NewsCache` table) to avoid re-fetching.

**yfinance tickers**: NSE stocks use `.NS` suffix (e.g., `HAL.NS`). If a market holiday falls on the target date, `_next_trading_day_price()` looks forward up to 5 days.

**Backtest vs live**: `news_agent.get_news(live=True)` → RSS feeds; `live=False` → GDELT + SQLite cache.

## Adding a New Country

1. Add the country to `COUNTRY_RSS_FEEDS` and `COUNTRY_GDELT_CODES` in `news_agent.py`
2. Create `src/config/<country>_stocks.json` with the same schema as `india_stocks.json`
3. Update `recommendation_agent.py` to load the correct stock file based on `country_code`
4. Add the country to `COUNTRIES` dict in `src/ui/app.py`
