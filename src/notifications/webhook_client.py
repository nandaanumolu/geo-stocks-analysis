import requests
from src.models.daily_picks import DailyPicksResult


def send_daily_picks(webhook_url: str, result: DailyPicksResult) -> tuple[bool, str]:
    payload = {
        "type": "daily_picks",
        "generated_for": result.generated_for,
        "overall_sentiment": result.overall_sentiment,
        "events_detected": result.events_detected,
        "news_count": result.news_count,
        "no_picks_reason": result.no_picks_reason,
        "picks": [
            {
                "ticker": p.ticker,
                "company_name": p.company_name,
                "sector": p.sector,
                "signal": p.signal,
                "confidence": p.confidence,
                "risk_level": p.risk_level,
                "last_price": p.last_price,
                "expected_return_min": p.expected_return_min,
                "expected_return_max": p.expected_return_max,
                "stop_loss_pct": p.stop_loss_pct,
                "reasoning": p.reasoning,
                "entry_note": p.entry_note,
                "exit_note": p.exit_note,
            }
            for p in result.picks
        ],
    }
    return _post(webhook_url, payload)


def send_eod_report(
    webhook_url: str, report_text: str, trade_date: str, post_mortem: str = ""
) -> tuple[bool, str]:
    payload = {
        "type": "eod_report",
        "trade_date": trade_date,
        "report": report_text,
        "post_mortem": post_mortem,
    }
    return _post(webhook_url, payload)


def _post(url: str, payload: dict) -> tuple[bool, str]:
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code < 300:
            return True, ""
        return False, f"Webhook {r.status_code}: {r.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, str(e)
