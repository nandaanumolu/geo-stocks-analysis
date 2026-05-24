from datetime import date
from unittest.mock import patch, MagicMock
from src.agents.backtest_agent import run_backtest, _compute_metrics
from src.models.backtest import BacktestResult, BacktestStock, PerformanceMetrics
from src.models.events import GeoAnalysis, GeoEvent, SectorImpact
from src.models.recommendations import StockRecommendation


def _make_backtest_stock(ticker: str, signal: str, return_pct: float | None) -> BacktestStock:
    correct: bool | None = None
    if return_pct is not None:
        if signal == "BUY":
            correct = return_pct > 0
        elif signal == "SELL":
            correct = return_pct < 0
    return BacktestStock(
        ticker=ticker,
        company_name=f"{ticker} Corp",
        sector="defense",
        signal=signal,
        confidence=75.0,
        reasoning="test",
        entry_price=100.0,
        current_price=100 + return_pct if return_pct is not None else None,
        return_pct=return_pct,
        correct_call=correct,
    )


class TestComputeMetrics:
    def test_perfect_hit_rate_when_all_correct(self):
        stocks = [
            _make_backtest_stock("HAL.NS", "BUY", 15.0),
            _make_backtest_stock("TCS.NS", "BUY", 8.0),
            _make_backtest_stock("INDIGO.NS", "SELL", -10.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=5.0)
        assert metrics.hit_rate_pct == 100.0

    def test_zero_hit_rate_when_all_wrong(self):
        stocks = [
            _make_backtest_stock("HAL.NS", "BUY", -5.0),
            _make_backtest_stock("INDIGO.NS", "SELL", 10.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=5.0)
        assert metrics.hit_rate_pct == 0.0

    def test_avg_return_calculation(self):
        stocks = [
            _make_backtest_stock("A.NS", "BUY", 20.0),
            _make_backtest_stock("B.NS", "BUY", -10.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=None)
        assert metrics.avg_return_pct == 5.0

    def test_alpha_computed_as_avg_return_minus_nifty(self):
        stocks = [
            _make_backtest_stock("HAL.NS", "BUY", 15.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=8.0)
        assert metrics.alpha_vs_nifty_pct == 7.0

    def test_alpha_is_none_when_nifty_unavailable(self):
        stocks = [_make_backtest_stock("HAL.NS", "BUY", 15.0)]
        metrics = _compute_metrics(stocks, nifty_return=None)
        assert metrics.alpha_vs_nifty_pct is None

    def test_portfolio_value_calculation(self):
        stocks = [
            _make_backtest_stock("HAL.NS", "BUY", 10.0),
            _make_backtest_stock("BEL.NS", "BUY", -10.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=None)
        # ₹10,000 × 1.10 + ₹10,000 × 0.90 = ₹11,000 + ₹9,000 = ₹20,000
        assert metrics.portfolio_value == 20_000.0

    def test_empty_stocks_returns_zero_metrics(self):
        metrics = _compute_metrics([], nifty_return=5.0)
        assert metrics.hit_rate_pct == 0.0
        assert metrics.avg_return_pct == 0.0

    def test_best_and_worst_picks_identified(self):
        stocks = [
            _make_backtest_stock("WIN.NS", "BUY", 30.0),
            _make_backtest_stock("LOSE.NS", "BUY", -20.0),
        ]
        metrics = _compute_metrics(stocks, nifty_return=None)
        assert metrics.best_pick == "WIN.NS"
        assert metrics.worst_pick == "LOSE.NS"


class TestRunBacktest:
    def _make_mock_analysis(self) -> GeoAnalysis:
        return GeoAnalysis(
            events=[GeoEvent(
                type="india_pakistan_tension",
                description="Border tensions",
                affected_sectors=[
                    SectorImpact(sector="defense", direction="positive", magnitude="high", reasoning="test")
                ],
                time_horizon="short_term",
                confidence=0.85,
            )],
            overall_market_sentiment="bearish",
        )

    def test_backtest_returns_result_with_correct_date(self):
        test_date = date(2024, 2, 1)
        mock_analysis = self._make_mock_analysis()
        mock_recs = [StockRecommendation(
            ticker="HAL.NS", company_name="HAL", sector="defense",
            signal="BUY", confidence=80.0, reasoning="defense sector boost",
        )]

        with patch("src.agents.backtest_agent.news_agent.get_news", return_value=[]), \
             patch("src.agents.backtest_agent.analysis_agent.analyze_news", return_value=mock_analysis), \
             patch("src.agents.backtest_agent.recommendation_agent.generate_recommendations", return_value=mock_recs), \
             patch("src.agents.backtest_agent.stock_client.get_price_on_date", return_value=1500.0), \
             patch("src.agents.backtest_agent.stock_client.get_current_price", return_value=1800.0), \
             patch("src.agents.backtest_agent.stock_client.get_nifty50_return", return_value=12.5), \
             patch("src.agents.backtest_agent._save_run"):
            result = run_backtest("IN", test_date)

        assert isinstance(result, BacktestResult)
        assert result.analysis_date == "2024-02-01"
        assert result.country == "IN"

    def test_backtest_calculates_return_pct(self):
        test_date = date(2024, 2, 1)
        mock_analysis = self._make_mock_analysis()
        mock_recs = [StockRecommendation(
            ticker="HAL.NS", company_name="HAL", sector="defense",
            signal="BUY", confidence=80.0, reasoning="defense sector boost",
        )]

        with patch("src.agents.backtest_agent.news_agent.get_news", return_value=[]), \
             patch("src.agents.backtest_agent.analysis_agent.analyze_news", return_value=mock_analysis), \
             patch("src.agents.backtest_agent.recommendation_agent.generate_recommendations", return_value=mock_recs), \
             patch("src.agents.backtest_agent.stock_client.get_price_on_date", return_value=1000.0), \
             patch("src.agents.backtest_agent.stock_client.get_current_price", return_value=1200.0), \
             patch("src.agents.backtest_agent.stock_client.get_nifty50_return", return_value=8.0), \
             patch("src.agents.backtest_agent._save_run"):
            result = run_backtest("IN", test_date)

        assert len(result.stocks) == 1
        assert result.stocks[0].return_pct == 20.0
        assert result.stocks[0].correct_call is True

    def test_backtest_nifty_benchmark_comparison(self):
        test_date = date(2024, 10, 1)
        mock_analysis = self._make_mock_analysis()
        mock_recs = [StockRecommendation(
            ticker="HAL.NS", company_name="HAL", sector="defense",
            signal="BUY", confidence=80.0, reasoning="x",
        )]

        with patch("src.agents.backtest_agent.news_agent.get_news", return_value=[]), \
             patch("src.agents.backtest_agent.analysis_agent.analyze_news", return_value=mock_analysis), \
             patch("src.agents.backtest_agent.recommendation_agent.generate_recommendations", return_value=mock_recs), \
             patch("src.agents.backtest_agent.stock_client.get_price_on_date", return_value=1000.0), \
             patch("src.agents.backtest_agent.stock_client.get_current_price", return_value=1150.0), \
             patch("src.agents.backtest_agent.stock_client.get_nifty50_return", return_value=7.5), \
             patch("src.agents.backtest_agent._save_run"):
            result = run_backtest("IN", test_date)

        assert result.metrics is not None
        assert isinstance(result.metrics.nifty50_return_pct, float)
        assert result.metrics.alpha_vs_nifty_pct == round(15.0 - 7.5, 2)
