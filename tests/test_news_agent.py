from datetime import date
from unittest.mock import patch, MagicMock
from src.agents.news_agent import get_news, _is_geopolitical
from src.models.events import NewsItem


def _make_article(title: str) -> NewsItem:
    return NewsItem(title=title, url="http://example.com", source="test")


class TestIsGeopolitical:
    def test_border_tension_is_geopolitical(self):
        assert _is_geopolitical("India Pakistan border tension escalates")

    def test_sports_news_is_not_geopolitical(self):
        assert not _is_geopolitical("India wins cricket match against Australia")

    def test_trade_war_is_geopolitical(self):
        assert _is_geopolitical("US China trade war impacts markets")

    def test_rbi_policy_is_geopolitical(self):
        assert _is_geopolitical("RBI announces rate decision amid inflation concerns")

    def test_budget_is_geopolitical(self):
        assert _is_geopolitical("Finance minister presents union budget 2024")

    def test_crude_oil_is_geopolitical(self):
        assert _is_geopolitical("Crude oil price surges as OPEC cuts production")

    def test_defence_is_geopolitical(self):
        assert _is_geopolitical("India ramps up defence spending on border concerns")


class TestGetNews:
    def test_historical_fetch_uses_guardian_as_primary(self):
        guardian_articles = [
            _make_article("India budget 2024 infrastructure spending boost"),
            _make_article("RBI holds rate as inflation cools"),
        ]
        with patch("src.agents.news_agent.guardian_client.fetch_geopolitical_news", return_value=guardian_articles) as mock_guardian, \
             patch("src.agents.news_agent._load_from_cache", return_value=[]), \
             patch("src.agents.news_agent._cache_articles"):
            result = get_news("IN", date(2024, 2, 1), live=False)

        mock_guardian.assert_called_once()
        assert len(result) > 0
        assert all(isinstance(a, NewsItem) for a in result)

    def test_cache_is_returned_when_populated(self):
        cached = [_make_article("Cached diplomatic tensions article")]
        with patch("src.agents.news_agent._load_from_cache", return_value=cached):
            result = get_news("IN", date(2024, 2, 1), live=False)

        assert result == cached

    def test_live_mode_calls_rss_first(self):
        rss_articles = [_make_article("India Pakistan border tension alert")]
        with patch("src.agents.news_agent._fetch_rss_news", return_value=rss_articles) as mock_rss, \
             patch("src.agents.news_agent.guardian_client.fetch_geopolitical_news") as mock_guardian:
            result = get_news("IN", date.today(), live=True)

        mock_rss.assert_called_once()
        mock_guardian.assert_not_called()
        assert result == rss_articles

    def test_live_mode_falls_back_to_guardian_when_rss_empty(self):
        guardian_articles = [_make_article("India RBI rate decision today")]
        with patch("src.agents.news_agent._fetch_rss_news", return_value=[]), \
             patch("src.agents.news_agent.guardian_client.fetch_geopolitical_news", return_value=guardian_articles), \
             patch("src.agents.news_agent.gdelt_client.fetch_geopolitical_news", return_value=[]):
            result = get_news("IN", date.today(), live=True)

        assert result == guardian_articles

    def test_empty_result_when_all_sources_fail(self):
        with patch("src.agents.news_agent.guardian_client.fetch_geopolitical_news", return_value=[]), \
             patch("src.agents.news_agent.gdelt_client.fetch_geopolitical_news", return_value=[]), \
             patch("src.agents.news_agent._load_from_cache", return_value=[]), \
             patch("src.agents.news_agent._cache_articles"):
            result = get_news("IN", date(2024, 1, 1), live=False)

        assert isinstance(result, list)
