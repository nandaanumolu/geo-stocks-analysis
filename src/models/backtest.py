from pydantic import BaseModel, Field


class BacktestStock(BaseModel):
    ticker: str
    company_name: str
    sector: str
    signal: str
    confidence: float
    reasoning: str
    entry_price: float | None = None
    current_price: float | None = None
    return_pct: float | None = None
    correct_call: bool | None = None


class PerformanceMetrics(BaseModel):
    total_recommendations: int
    correct_calls: int
    hit_rate_pct: float
    avg_return_pct: float
    best_pick: str | None = None
    worst_pick: str | None = None
    nifty50_return_pct: float | None = None
    alpha_vs_nifty_pct: float | None = None
    portfolio_value: float | None = None  # assumes ₹10,000 per BUY stock


class BacktestResult(BaseModel):
    country: str
    analysis_date: str
    news_count: int
    events_detected: list[str] = Field(default_factory=list)
    overall_sentiment: str
    stocks: list[BacktestStock] = Field(default_factory=list)
    metrics: PerformanceMetrics | None = None
    sample_headlines: list[str] = Field(default_factory=list)  # shown when no events detected
    no_events_reason: str | None = None  # human-readable explanation
