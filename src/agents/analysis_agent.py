import json
import logging
import anthropic
from src.config.settings import get_settings
from src.models.events import NewsItem, GeoAnalysis

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a geo-political financial analyst specializing in Indian equity markets (NSE/BSE).

Given a list of news articles, identify geo-political events, their market impact, and specific sectors affected.

Always respond with ONLY valid JSON matching this exact schema:
{
  "events": [
    {
      "type": "<snake_case_event_type>",
      "description": "<1-2 sentence summary>",
      "affected_sectors": [
        {
          "sector": "<sector_name>",
          "direction": "<positive|negative|neutral>",
          "magnitude": "<low|medium|high>",
          "reasoning": "<why this sector is affected>"
        }
      ],
      "time_horizon": "<short_term|medium_term|long_term>",
      "confidence": <0.0 to 1.0>
    }
  ],
  "overall_market_sentiment": "<bullish|bearish|neutral>",
  "key_risks": ["<risk1>", "<risk2>"]
}

Common event types: india_pakistan_tension, india_china_tension, oil_price_surge, oil_price_drop,
rupee_depreciation, rupee_appreciation, us_fed_rate_hike, us_fed_rate_cut, india_budget_infrastructure,
india_budget_defense, india_election_results, global_recession_fears, monsoon_deficient, monsoon_normal,
west_asia_conflict, rbi_rate_hike, rbi_rate_cut, india_us_trade_deal, sanctions_on_russia,
india_china_trade_dispute, domestic_political_instability.

Sectors: defense, it, banking, oil_gas, pharma, fmcg, auto, telecom, metals, aviation,
chemicals, infrastructure, real_estate, fertilizers, renewable_energy.

If news is irrelevant or non-geopolitical, return events=[] and sentiment=neutral.
Do NOT wrap the JSON in markdown code blocks."""

def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _get_recent_learnings(days: int = 7) -> str:
    """Query DailyLearning table and return a formatted string of recent lessons."""
    try:
        from src.data.db import DailyLearning, get_session, init_db
        init_db()
        session = get_session()
        rows = (
            session.query(DailyLearning)
            .order_by(DailyLearning.trade_date.desc())
            .limit(days)
            .all()
        )
        session.close()

        if not rows:
            return ""

        lines = ["LESSONS FROM RECENT PREDICTIONS (use these to improve accuracy):", ""]
        for row in rows:
            lines.append(
                f"[{row.trade_date}] Hit rate: {row.hit_rate:.0f}%, "
                f"Avg return: {row.avg_return_pct:+.2f}%"
            )
            if row.what_worked:
                lines.append(f"  Worked: {row.what_worked}")
            if row.what_failed:
                lines.append(f"  Failed: {row.what_failed}")
            try:
                lessons = json.loads(row.lessons) if row.lessons else []
            except Exception:
                lessons = []
            for lesson in lessons:
                lines.append(f"  → {lesson}")
            lines.append("")

        return "\n".join(lines).rstrip()
    except Exception:
        log.exception("_get_recent_learnings: failed to load learnings")
        return ""


def _build_user_prompt(articles: list[NewsItem]) -> str:
    learnings = _get_recent_learnings()
    articles_json = json.dumps(
        [{"title": a.title, "source": a.source, "published_at": a.published_at} for a in articles[:30]],
        indent=2
    )
    analysis_request = (
        f"Analyze these news articles for geo-political events affecting Indian stock markets:\n\n{articles_json}"
    )
    if learnings:
        return f"{learnings}\n\n{analysis_request}"
    return analysis_request


def _parse_response(text: str) -> GeoAnalysis:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    data = json.loads(text)
    return GeoAnalysis.model_validate(data)


def analyze_news(articles: list[NewsItem]) -> GeoAnalysis:
    """Use Claude to analyze news articles and return structured geo-political analysis."""
    if not articles:
        return GeoAnalysis()

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": _build_user_prompt(articles)}
        ],
    )

    raw = response.content[0].text

    try:
        return _parse_response(raw)
    except (json.JSONDecodeError, Exception):
        # Retry with explicit fix instruction
        fix_response = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": _build_user_prompt(articles)},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "The JSON was invalid. Return ONLY the corrected valid JSON, no markdown."},
            ],
        )
        try:
            return _parse_response(fix_response.content[0].text)
        except Exception:
            return GeoAnalysis()
