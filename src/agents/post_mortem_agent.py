"""
Post-mortem agent: reviews today's picks against actual closing prices,
calls Claude for honest analysis, and stores learnings in DailyLearning table.
"""
import json
import logging
from typing import Optional

import anthropic

from src.config.settings import get_settings
from src.data import stock_client
from src.data.db import DailyLearning, PickDetail, get_session, init_db

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a geo-political stock analyst reviewing your own intraday trading predictions.
Analyze the gap between what was predicted and what actually happened. Be honest and specific.

Return ONLY valid JSON (no markdown):
{
  "per_pick": [
    {
      "ticker": "<ticker>",
      "outcome": "hit|miss|unknown",
      "reason": "<why it worked or failed>"
    }
  ],
  "what_worked": "<patterns that led to correct predictions>",
  "what_failed": "<patterns that led to wrong predictions>",
  "event_accuracy": "<which event types were accurately predictive today>",
  "lessons": ["<specific actionable lesson for future predictions>"],
  "confidence_calibration": "<were high-confidence picks more accurate?>"
}"""


def _build_prompt(picks_data: list[dict]) -> str:
    return (
        "Review these intraday stock predictions vs actual closing prices.\n\n"
        "For each pick, the predicted_return_min/max is what we expected.\n"
        "The actual_return_pct is what actually happened (null means price was unavailable).\n\n"
        f"{json.dumps(picks_data, indent=2)}\n\n"
        "Analyze what worked, what failed, and provide specific lessons for improving future predictions."
    )


def run_post_mortem(trade_date: str) -> Optional[str]:
    """
    Load today's PickDetail rows, fetch actual closing prices, call Claude for analysis,
    store result in DailyLearning, and return a formatted summary string.
    Returns None if no picks found or on unrecoverable error.
    """
    # --- Load picks from DB ---
    try:
        init_db()
        session = get_session()
        picks = session.query(PickDetail).filter_by(trade_date=trade_date).all()
        session.close()
    except Exception:
        log.exception("post_mortem: failed to load PickDetail rows")
        return None

    if not picks:
        log.info(f"post_mortem: no PickDetail rows found for {trade_date}")
        return None

    # --- Fetch actual closing prices and compute returns ---
    picks_data = []
    hits, total_evaluated = 0, 0

    for p in picks:
        try:
            actual_price = stock_client.get_current_price(p.ticker)
        except Exception:
            actual_price = None

        actual_return_pct = None
        if actual_price and p.ref_price and p.ref_price > 0:
            actual_return_pct = round((actual_price - p.ref_price) / p.ref_price * 100, 2)
            total_evaluated += 1
            # A "hit" means the actual return is at least 50% of the min predicted return
            if actual_return_pct >= (p.predicted_return_min or 0) * 0.5:
                hits += 1

        picks_data.append({
            "ticker": p.ticker,
            "company_name": p.company_name,
            "sector": p.sector,
            "signal": p.signal,
            "confidence": p.confidence,
            "risk_level": p.risk_level,
            "ref_price": p.ref_price,
            "actual_price": actual_price,
            "actual_return_pct": actual_return_pct,
            "predicted_return_min": p.predicted_return_min,
            "predicted_return_max": p.predicted_return_max,
            "reasoning": p.reasoning,
        })

    hit_rate = (hits / total_evaluated * 100) if total_evaluated > 0 else 0.0
    avg_return = (
        sum(d["actual_return_pct"] for d in picks_data if d["actual_return_pct"] is not None)
        / total_evaluated
        if total_evaluated > 0
        else 0.0
    )

    # --- Call Claude for honest analysis ---
    raw_json = ""
    analysis: dict = {}
    try:
        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(picks_data)}],
        )
        raw_json = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw_json.startswith("```"):
            lines = raw_json.split("\n")
            raw_json = "\n".join(lines[1:-1])

        analysis = json.loads(raw_json)
    except Exception:
        log.exception("post_mortem: Claude call or JSON parse failed")
        # Proceed with partial data

    what_worked = analysis.get("what_worked", "")
    what_failed = analysis.get("what_failed", "")
    lessons = analysis.get("lessons", [])

    # --- Store in DailyLearning ---
    try:
        init_db()
        session = get_session()
        # Upsert: delete any existing record for this date then insert fresh
        session.query(DailyLearning).filter_by(trade_date=trade_date).delete()
        session.add(DailyLearning(
            trade_date=trade_date,
            hit_rate=round(hit_rate, 2),
            avg_return_pct=round(avg_return, 2),
            total_picks=len(picks),
            what_worked=what_worked,
            what_failed=what_failed,
            lessons=json.dumps(lessons),
            raw_json=raw_json,
        ))
        session.commit()
        session.close()
        log.info(f"post_mortem: saved DailyLearning for {trade_date}")
    except Exception:
        log.exception("post_mortem: failed to save DailyLearning")

    # --- Build summary string ---
    lines = [
        f"*Post-Mortem — {trade_date}*",
        f"Hit Rate: {hit_rate:.0f}%  |  Avg Return: {avg_return:+.2f}%  |  Picks Evaluated: {total_evaluated}/{len(picks)}",
    ]
    if what_worked:
        lines.append(f"What Worked: {what_worked}")
    if what_failed:
        lines.append(f"What Failed: {what_failed}")
    if lessons:
        lines.append("Lessons:")
        for lesson in lessons:
            lines.append(f"  • {lesson}")

    return "\n".join(lines)
