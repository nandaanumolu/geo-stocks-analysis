import json
from pathlib import Path
from src.models.events import GeoAnalysis, SectorImpact
from src.models.recommendations import StockRecommendation

_STOCKS_PATH = Path(__file__).parent.parent / "config" / "india_stocks.json"
_MAGNITUDE_WEIGHT = {"low": 0.4, "medium": 0.7, "high": 1.0}
_MIN_CONFIDENCE = 40.0


def _load_stock_universe() -> list[dict]:
    with open(_STOCKS_PATH) as f:
        return json.load(f)


def _resolve_sector_signals(analysis: GeoAnalysis) -> dict[str, float]:
    """Build a sector → net_score map from all detected events.

    Positive score = bullish signal, negative = bearish.
    Score magnitude reflects event confidence × sector impact magnitude.
    """
    sector_scores: dict[str, float] = {}

    for event in analysis.events:
        for impact in event.affected_sectors:
            weight = _MAGNITUDE_WEIGHT.get(impact.magnitude, 0.5)
            score = event.confidence * weight * 100
            if impact.direction == "negative":
                score = -score

            current = sector_scores.get(impact.sector, 0.0)
            sector_scores[impact.sector] = current + score

    return sector_scores


def _build_reasoning(stock: dict, triggered_events: list[str], impacts: list[SectorImpact]) -> str:
    impact_summaries = [f"{i.sector} is {i.direction} ({i.magnitude}): {i.reasoning}" for i in impacts[:3]]
    events_str = ", ".join(triggered_events) if triggered_events else "current geo-political climate"
    impact_str = "; ".join(impact_summaries) if impact_summaries else "sector-level geo-political signals"
    return f"{stock['name']} ({stock['sector']}) affected by {events_str}. {impact_str}."


def generate_recommendations(analysis: GeoAnalysis) -> list[StockRecommendation]:
    """Map geo-political analysis to stock-level BUY/SELL/HOLD recommendations."""
    stocks = _load_stock_universe()
    sector_scores = _resolve_sector_signals(analysis)

    if not sector_scores:
        return []

    recommendations: list[StockRecommendation] = []

    for stock in stocks:
        sector = stock["sector"]
        if sector not in sector_scores:
            continue

        net_score = sector_scores[sector]
        confidence = min(abs(net_score), 100.0)

        if confidence < _MIN_CONFIDENCE:
            continue

        signal = "BUY" if net_score > 0 else "SELL"

        # Collect which events triggered this and their impacts
        triggered_events: list[str] = []
        relevant_impacts: list[SectorImpact] = []
        for event in analysis.events:
            for impact in event.affected_sectors:
                if impact.sector == sector:
                    triggered_events.append(event.type)
                    relevant_impacts.append(impact)

        # Determine dominant time horizon from triggering events
        horizons = [e.time_horizon for e in analysis.events if e.type in triggered_events]
        time_horizon = horizons[0] if horizons else "medium_term"

        recommendations.append(StockRecommendation(
            ticker=stock["ticker"],
            company_name=stock["name"],
            sector=sector,
            signal=signal,
            confidence=round(confidence, 1),
            reasoning=_build_reasoning(stock, list(set(triggered_events)), relevant_impacts),
            time_horizon=time_horizon,
            triggered_by=list(set(triggered_events)),
        ))

    recommendations.sort(key=lambda r: r.confidence, reverse=True)
    return recommendations
