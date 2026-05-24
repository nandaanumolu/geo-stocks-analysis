import json
from unittest.mock import patch, MagicMock
from src.agents.analysis_agent import analyze_news, _parse_response, _build_user_prompt
from src.models.events import NewsItem, GeoAnalysis, GeoEvent, SectorImpact


def _make_article(title: str) -> NewsItem:
    return NewsItem(title=title, url="http://example.com", source="test", published_at="2024-01-15")


def _mock_analysis_response(events: list[dict], sentiment: str = "neutral") -> str:
    return json.dumps({
        "events": events,
        "overall_market_sentiment": sentiment,
        "key_risks": ["market volatility"],
    })


BORDER_TENSION_RESPONSE = _mock_analysis_response(
    events=[{
        "type": "india_pakistan_tension",
        "description": "Escalating border standoff between India and Pakistan.",
        "affected_sectors": [
            {"sector": "defense", "direction": "positive", "magnitude": "high",
             "reasoning": "Defense spending expected to increase significantly."},
            {"sector": "aviation", "direction": "negative", "magnitude": "medium",
             "reasoning": "Airspace restrictions and reduced travel."},
        ],
        "time_horizon": "short_term",
        "confidence": 0.88,
    }],
    sentiment="bearish",
)

OIL_SURGE_RESPONSE = _mock_analysis_response(
    events=[{
        "type": "oil_price_surge",
        "description": "Oil prices spike due to West Asia conflict.",
        "affected_sectors": [
            {"sector": "oil_gas", "direction": "positive", "magnitude": "high",
             "reasoning": "Higher crude prices benefit upstream producers."},
            {"sector": "aviation", "direction": "negative", "magnitude": "high",
             "reasoning": "Jet fuel costs rise sharply, squeezing margins."},
            {"sector": "chemicals", "direction": "negative", "magnitude": "medium",
             "reasoning": "Raw material costs increase for paint and chemicals companies."},
        ],
        "time_horizon": "medium_term",
        "confidence": 0.92,
    }],
    sentiment="bearish",
)


class TestParseResponse:
    def test_valid_json_parses_to_geo_analysis(self):
        result = _parse_response(BORDER_TENSION_RESPONSE)
        assert isinstance(result, GeoAnalysis)
        assert len(result.events) == 1
        assert result.events[0].type == "india_pakistan_tension"

    def test_markdown_wrapped_json_is_handled(self):
        wrapped = f"```json\n{BORDER_TENSION_RESPONSE}\n```"
        result = _parse_response(wrapped)
        assert isinstance(result, GeoAnalysis)

    def test_confidence_within_bounds(self):
        result = _parse_response(BORDER_TENSION_RESPONSE)
        for event in result.events:
            assert 0.0 <= event.confidence <= 1.0


class TestAnalyzeNews:
    def test_border_tension_news_detects_defense_positive(self):
        articles = [
            _make_article("India Pakistan border tension escalates after military standoff"),
            _make_article("Pakistan denies ceasefire violations at Line of Control"),
        ]
        mock_content = MagicMock()
        mock_content.text = BORDER_TENSION_RESPONSE
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        with patch("src.agents.analysis_agent._get_client") as mock_get_client:
            mock_get_client.return_value.messages.create.return_value = mock_response
            result = analyze_news(articles)

        assert isinstance(result, GeoAnalysis)
        assert any(e.type == "india_pakistan_tension" for e in result.events)
        defense_impacts = [
            impact for e in result.events
            for impact in e.affected_sectors
            if impact.sector == "defense"
        ]
        assert any(i.direction == "positive" for i in defense_impacts)

    def test_oil_price_surge_triggers_correct_sectors(self):
        articles = [_make_article("Oil prices surge amid West Asia conflict, Brent hits $110")]
        mock_content = MagicMock()
        mock_content.text = OIL_SURGE_RESPONSE
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        with patch("src.agents.analysis_agent._get_client") as mock_get_client:
            mock_get_client.return_value.messages.create.return_value = mock_response
            result = analyze_news(articles)

        sectors = {
            impact.sector: impact.direction
            for e in result.events
            for impact in e.affected_sectors
        }
        assert sectors.get("oil_gas") == "positive"
        assert sectors.get("aviation") == "negative"

    def test_empty_articles_returns_empty_analysis(self):
        result = analyze_news([])
        assert isinstance(result, GeoAnalysis)
        assert result.events == []
        assert result.overall_market_sentiment == "neutral"

    def test_output_is_valid_pydantic_model(self):
        articles = [_make_article("India border tension and military conflict")]
        mock_content = MagicMock()
        mock_content.text = BORDER_TENSION_RESPONSE
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        with patch("src.agents.analysis_agent._get_client") as mock_get_client:
            mock_get_client.return_value.messages.create.return_value = mock_response
            result = analyze_news(articles)

        assert isinstance(result, GeoAnalysis)
        assert isinstance(result.events, list)
        for event in result.events:
            assert isinstance(event, GeoEvent)
            for impact in event.affected_sectors:
                assert isinstance(impact, SectorImpact)
