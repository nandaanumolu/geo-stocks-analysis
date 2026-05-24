from datetime import date
from pydantic import BaseModel, Field
from typing import Literal


class DailyPick(BaseModel):
    ticker: str
    company_name: str
    sector: str
    signal: Literal["BUY", "SELL"]
    trade_date: str                  # YYYY-MM-DD — the day to enter and exit
    entry_note: str                  # "Buy at market open 9:15 AM IST"
    exit_note: str                   # "Sell before 3:15 PM IST close"
    risk_level: Literal["low", "medium", "high"]
    last_price: float = 0.0          # last closing price in INR
    expected_return_min: float       # e.g. 1.5  (%)
    expected_return_max: float       # e.g. 4.0  (%)
    stop_loss_pct: float             # e.g. 1.5  (%)
    confidence: float                # 0–100
    reasoning: str                   # why this stock moves today
    triggered_by: list[str]          # geo event types driving the pick


class DailyPicksResult(BaseModel):
    generated_for: str               # YYYY-MM-DD trade date
    news_count: int
    events_detected: list[str] = Field(default_factory=list)
    overall_sentiment: str
    picks: list[DailyPick] = Field(default_factory=list)
    no_picks_reason: str | None = None
