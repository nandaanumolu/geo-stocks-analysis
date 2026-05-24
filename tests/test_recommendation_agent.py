from src.agents.recommendation_agent import generate_recommendations, _resolve_sector_signals
from src.models.events import GeoAnalysis, GeoEvent, SectorImpact
from src.models.recommendations import StockRecommendation


def _make_analysis(sector: str, direction: str, magnitude: str = "high", confidence: float = 0.9) -> GeoAnalysis:
    return GeoAnalysis(
        events=[
            GeoEvent(
                type="india_pakistan_tension",
                description="Test event",
                affected_sectors=[
                    SectorImpact(sector=sector, direction=direction, magnitude=magnitude, reasoning="test")
                ],
                time_horizon="short_term",
                confidence=confidence,
            )
        ],
        overall_market_sentiment="bearish",
        key_risks=[],
    )


class TestResolveSectorSignals:
    def test_positive_sector_has_positive_score(self):
        analysis = _make_analysis("defense", "positive")
        scores = _resolve_sector_signals(analysis)
        assert scores.get("defense", 0) > 0

    def test_negative_sector_has_negative_score(self):
        analysis = _make_analysis("aviation", "negative")
        scores = _resolve_sector_signals(analysis)
        assert scores.get("aviation", 0) < 0

    def test_empty_analysis_returns_empty_scores(self):
        scores = _resolve_sector_signals(GeoAnalysis())
        assert scores == {}

    def test_magnitude_affects_score(self):
        high = _resolve_sector_signals(_make_analysis("defense", "positive", "high"))
        low = _resolve_sector_signals(_make_analysis("defense", "positive", "low"))
        assert high["defense"] > low["defense"]


class TestGenerateRecommendations:
    def test_defense_signal_returns_defense_stocks(self):
        analysis = _make_analysis("defense", "positive", "high", 0.9)
        recs = generate_recommendations(analysis)
        tickers = [r.ticker for r in recs]
        assert any(t in tickers for t in ["HAL.NS", "BEL.NS", "BDL.NS"])

    def test_buy_signal_for_positive_sector(self):
        analysis = _make_analysis("defense", "positive", "high", 0.9)
        recs = generate_recommendations(analysis)
        defense_recs = [r for r in recs if r.sector == "defense"]
        assert all(r.signal == "BUY" for r in defense_recs)

    def test_sell_signal_for_negative_sector(self):
        analysis = _make_analysis("aviation", "negative", "high", 0.9)
        recs = generate_recommendations(analysis)
        aviation_recs = [r for r in recs if r.sector == "aviation"]
        assert all(r.signal == "SELL" for r in aviation_recs)

    def test_confidence_scores_within_valid_range(self):
        analysis = _make_analysis("it", "positive", "medium", 0.75)
        recs = generate_recommendations(analysis)
        for r in recs:
            assert 0.0 <= r.confidence <= 100.0

    def test_no_recommendations_for_empty_analysis(self):
        recs = generate_recommendations(GeoAnalysis())
        assert recs == []

    def test_recommendations_sorted_by_confidence_descending(self):
        analysis = GeoAnalysis(
            events=[
                GeoEvent(
                    type="india_china_tension",
                    description="Test",
                    affected_sectors=[
                        SectorImpact(sector="defense", direction="positive", magnitude="high", reasoning="x"),
                        SectorImpact(sector="it", direction="positive", magnitude="low", reasoning="x"),
                    ],
                    time_horizon="medium_term",
                    confidence=0.85,
                )
            ],
            overall_market_sentiment="neutral",
        )
        recs = generate_recommendations(analysis)
        confidences = [r.confidence for r in recs]
        assert confidences == sorted(confidences, reverse=True)

    def test_recommendation_has_all_required_fields(self):
        analysis = _make_analysis("banking", "positive")
        recs = generate_recommendations(analysis)
        if recs:
            r = recs[0]
            assert isinstance(r, StockRecommendation)
            assert r.ticker
            assert r.company_name
            assert r.sector
            assert r.signal in ("BUY", "SELL", "HOLD")
            assert r.reasoning
