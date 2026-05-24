from datetime import date
from src.agents import news_agent, analysis_agent, recommendation_agent
from src.data import stock_client
from src.data.db import get_session, RecommendationRun, StockRecommendationDB, init_db
from src.models.backtest import BacktestResult, BacktestStock, PerformanceMetrics
from src.models.recommendations import StockRecommendation

_PORTFOLIO_PER_STOCK = 10_000.0  # ₹10,000 per BUY recommendation


def _compute_metrics(
    stocks: list[BacktestStock],
    nifty_return: float | None,
) -> PerformanceMetrics:
    evaluated = [s for s in stocks if s.return_pct is not None]
    if not evaluated:
        return PerformanceMetrics(
            total_recommendations=len(stocks),
            correct_calls=0,
            hit_rate_pct=0.0,
            avg_return_pct=0.0,
        )

    correct = sum(1 for s in evaluated if s.correct_call)
    returns = [s.return_pct for s in evaluated if s.return_pct is not None]
    avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0
    hit_rate = round(correct / len(evaluated) * 100, 1)

    buy_stocks = [s for s in evaluated if s.signal == "BUY" and s.return_pct is not None]
    portfolio_value = None
    if buy_stocks:
        portfolio_value = round(
            sum(_PORTFOLIO_PER_STOCK * (1 + (s.return_pct or 0) / 100) for s in buy_stocks), 2
        )

    sorted_by_return = sorted(evaluated, key=lambda s: s.return_pct or 0)
    best = sorted_by_return[-1].ticker if sorted_by_return else None
    worst = sorted_by_return[0].ticker if sorted_by_return else None

    alpha = round(avg_return - nifty_return, 2) if nifty_return is not None else None

    return PerformanceMetrics(
        total_recommendations=len(stocks),
        correct_calls=correct,
        hit_rate_pct=hit_rate,
        avg_return_pct=avg_return,
        best_pick=best,
        worst_pick=worst,
        nifty50_return_pct=nifty_return,
        alpha_vs_nifty_pct=alpha,
        portfolio_value=portfolio_value,
    )


def _save_run(
    country: str,
    analysis_date: date,
    analysis,
    recommendations: list[StockRecommendation],
    backtest_stocks: list[BacktestStock],
) -> None:
    init_db()
    session = get_session()
    try:
        run = RecommendationRun(
            country=country,
            analysis_date=analysis_date.isoformat(),
            is_backtest=True,
            overall_sentiment=analysis.overall_sentiment,
            key_events=[e.type for e in analysis.events],
        )
        session.add(run)
        session.flush()

        for bs in backtest_stocks:
            session.add(StockRecommendationDB(
                run_id=run.id,
                ticker=bs.ticker,
                company_name=bs.company_name,
                sector=bs.sector,
                signal=bs.signal,
                confidence=bs.confidence,
                reasoning=bs.reasoning,
                entry_price=bs.entry_price,
                current_price=bs.current_price,
                return_pct=bs.return_pct,
                correct_call=bs.correct_call,
            ))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _is_market_holiday(d: date) -> bool:
    """Return True for dates with structurally low market news."""
    return d.weekday() >= 5 or (d.month == 1 and d.day == 1)  # weekend or New Year


def run_backtest(country_code: str, target_date: date) -> BacktestResult:
    """Run the full backtest pipeline for a country and historical date."""
    today = date.today()

    articles = news_agent.get_news(country_code, target_date, live=False)
    geo_analysis = analysis_agent.analyze_news(articles)

    # If no events detected despite having articles, widen the search window by ±3 more days
    if not geo_analysis.events and articles:
        from src.data import guardian_client
        from datetime import timedelta
        extra = guardian_client.fetch_geopolitical_news(country_code, target_date, window_days=5)
        seen = {a.url for a in articles}
        new_articles = [a for a in extra if a.url not in seen]
        if new_articles:
            articles = articles + new_articles
            geo_analysis = analysis_agent.analyze_news(articles)

    recommendations = recommendation_agent.generate_recommendations(geo_analysis)

    nifty_return = stock_client.get_nifty50_return(target_date, today)

    backtest_stocks: list[BacktestStock] = []
    for rec in recommendations:
        entry_price = stock_client.get_price_on_date(rec.ticker, target_date)
        current_price = stock_client.get_current_price(rec.ticker)

        return_pct = None
        correct_call = None
        if entry_price and current_price and entry_price > 0:
            return_pct = round((current_price - entry_price) / entry_price * 100, 2)
            if rec.signal == "BUY":
                correct_call = return_pct > 0
            elif rec.signal == "SELL":
                correct_call = return_pct < 0

        backtest_stocks.append(BacktestStock(
            ticker=rec.ticker,
            company_name=rec.company_name,
            sector=rec.sector,
            signal=rec.signal,
            confidence=rec.confidence,
            reasoning=rec.reasoning,
            entry_price=entry_price,
            current_price=current_price,
            return_pct=return_pct,
            correct_call=correct_call,
        ))

    metrics = _compute_metrics(backtest_stocks, nifty_return)

    _save_run(country_code, target_date, geo_analysis, recommendations, backtest_stocks)

    # Build helpful context when nothing was detected
    no_events_reason = None
    sample_headlines: list[str] = []
    if not geo_analysis.events:
        sample_headlines = [a.title for a in articles[:8]]
        if not articles:
            no_events_reason = "No news articles found for this date. Try a nearby weekday."
        elif _is_market_holiday(target_date):
            no_events_reason = (
                f"{target_date.strftime('%B %d')} is a market holiday / weekend. "
                "News published on this day is typically year-in-review or outlook pieces "
                "with no actionable geo-political signals. Try the next trading day."
            )
        else:
            no_events_reason = (
                f"{len(articles)} articles were fetched but none contained specific "
                "geo-political events that move Indian markets. The news may be dominated "
                "by domestic non-financial topics. Try a nearby date or a date near a "
                "known event (budget, election, RBI decision, global conflict)."
            )

    return BacktestResult(
        country=country_code,
        analysis_date=target_date.isoformat(),
        news_count=len(articles),
        events_detected=[e.type for e in geo_analysis.events],
        overall_sentiment=geo_analysis.overall_market_sentiment,
        stocks=backtest_stocks,
        metrics=metrics,
        sample_headlines=sample_headlines,
        no_events_reason=no_events_reason,
    )
