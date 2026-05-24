from datetime import date, timedelta
from src.agents import news_agent, analysis_agent, recommendation_agent
from src.models.events import GeoAnalysis
from src.models.recommendations import StockRecommendation
from src.models.daily_picks import DailyPick, DailyPicksResult

# Sector base volatility: affects risk tier
_SECTOR_RISK = {
    "defense": "high",
    "metals": "high",
    "aviation": "high",
    "oil_gas": "medium",
    "banking": "medium",
    "auto": "medium",
    "infrastructure": "medium",
    "real_estate": "medium",
    "telecom": "medium",
    "chemicals": "medium",
    "fertilizers": "medium",
    "renewable_energy": "medium",
    "it": "low",
    "pharma": "low",
    "fmcg": "low",
}

# Expected intraday return range (%) by magnitude
_RETURN_RANGE = {
    "high":   (3.0, 6.0),
    "medium": (1.5, 3.5),
    "low":    (0.5, 2.0),
}

# Stop-loss % by final risk level
_STOP_LOSS = {"low": 1.0, "medium": 1.5, "high": 2.0}

_RISK_TIERS = ["low", "medium", "high"]


def _next_trading_day(from_date: date) -> date:
    """Return the next weekday (Mon–Fri) after from_date."""
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5:          # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def _risk_level(rec: StockRecommendation, analysis: GeoAnalysis, is_nifty50: bool) -> str:
    """Compute intraday risk tier: low / medium / high."""
    base = _SECTOR_RISK.get(rec.sector, "medium")
    tier = _RISK_TIERS.index(base)

    # High confidence → nudge risk down
    if rec.confidence >= 80:
        tier = max(0, tier - 1)
    elif rec.confidence < 55:
        tier = min(2, tier + 1)

    # Large-cap Nifty50 → nudge risk down
    if is_nifty50:
        tier = max(0, tier - 1)

    return _RISK_TIERS[tier]


def _expected_return(rec: StockRecommendation, analysis: GeoAnalysis) -> tuple[float, float]:
    """Estimate intraday expected return range from event magnitude."""
    magnitudes = []
    for event in analysis.events:
        if event.type in rec.triggered_by:
            for impact in event.affected_sectors:
                if impact.sector == rec.sector:
                    magnitudes.append(impact.magnitude)
    dominant = max(magnitudes, key=lambda m: ["low", "medium", "high"].index(m)) if magnitudes else "medium"
    return _RETURN_RANGE[dominant]


def _is_nifty50(ticker: str) -> bool:
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "config" / "india_stocks.json"
    with open(path) as f:
        stocks = json.load(f)
    return any(s["ticker"] == ticker and s.get("nifty50", False) for s in stocks)


def generate_daily_picks(country_code: str = "IN", top_n: int = 5) -> DailyPicksResult:
    """Generate intraday stock picks for the next trading day."""
    today = date.today()
    trade_date = _next_trading_day(today)
    trade_date_str = trade_date.isoformat()

    # --- news + AI analysis ---
    articles = news_agent.get_news(country_code, today, live=True)
    geo_analysis = analysis_agent.analyze_news(articles)
    recommendations = recommendation_agent.generate_recommendations(geo_analysis)

    if not recommendations:
        reason = (
            "No geo-political market-moving events detected in today's news. "
            "Check back after a major event (RBI decision, budget, border incident, oil spike)."
            if articles else
            "Could not fetch today's news. Check your internet connection."
        )
        return DailyPicksResult(
            generated_for=trade_date_str,
            news_count=len(articles),
            events_detected=[],
            overall_sentiment=geo_analysis.overall_market_sentiment,
            picks=[],
            no_picks_reason=reason,
        )

    # --- build picks from top recommendations ---
    picks: list[DailyPick] = []
    for rec in recommendations[:top_n * 2]:          # over-sample, then trim to top_n
        nifty50 = _is_nifty50(rec.ticker)
        risk = _risk_level(rec, geo_analysis, nifty50)
        ret_min, ret_max = _expected_return(rec, geo_analysis)
        stop = _STOP_LOSS[risk]

        entry_note = "Buy at market open — 9:15 AM IST"
        exit_note  = "Sell before market close — 3:15 PM IST (same day)"

        picks.append(DailyPick(
            ticker=rec.ticker,
            company_name=rec.company_name,
            sector=rec.sector,
            signal=rec.signal,
            trade_date=trade_date_str,
            entry_note=entry_note,
            exit_note=exit_note,
            risk_level=risk,
            expected_return_min=ret_min,
            expected_return_max=ret_max,
            stop_loss_pct=stop,
            confidence=rec.confidence,
            reasoning=rec.reasoning,
            triggered_by=rec.triggered_by,
        ))

        if len(picks) == top_n:
            break

    return DailyPicksResult(
        generated_for=trade_date_str,
        news_count=len(articles),
        events_detected=[e.type for e in geo_analysis.events],
        overall_sentiment=geo_analysis.overall_market_sentiment,
        picks=picks,
    )
