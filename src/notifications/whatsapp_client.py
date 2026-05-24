import requests
from src.models.daily_picks import DailyPicksResult, DailyPick

_CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

_RISK_ICON  = {"low": "🟢", "medium": "🟡", "high": "🔴"}
_RISK_LABEL = {"low": "LOW",  "medium": "MED",    "high": "HIGH"}


# ── Message formatter (shared by both providers) ──────────────────────────────

def _format_pick(idx: int, p: DailyPick) -> str:
    is_buy = p.signal == "BUY"
    sig  = "🟢 *BUY*" if is_buy else "🔴 *SELL/AVOID*"
    risk = f"{_RISK_ICON[p.risk_level]} {_RISK_LABEL[p.risk_level]} RISK"
    move = (f"+{p.expected_return_min:.1f}% → +{p.expected_return_max:.1f}%"
            if is_buy else
            f"-{p.expected_return_min:.1f}% → -{p.expected_return_max:.1f}%")
    sl   = (f"Cut if drops -{p.stop_loss_pct:.1f}%"
            if is_buy else
            f"Exit if rises +{p.stop_loss_pct:.1f}%")

    price_lines = ""
    if p.last_price and p.last_price > 0:
        ref = p.last_price
        if is_buy:
            tgt_lo = ref * (1 + p.expected_return_min / 100)
            tgt_hi = ref * (1 + p.expected_return_max / 100)
            sl_px  = ref * (1 - p.stop_loss_pct / 100)
        else:
            tgt_lo = ref * (1 - p.expected_return_min / 100)
            tgt_hi = ref * (1 - p.expected_return_max / 100)
            sl_px  = ref * (1 + p.stop_loss_pct / 100)
        price_lines = (
            f"\n   💰 Ref: ₹{ref:.2f}"
            f"\n   🎯 Target: ₹{min(tgt_lo,tgt_hi):.2f} → ₹{max(tgt_lo,tgt_hi):.2f}"
            f"\n   🛑 Stop ₹: ₹{sl_px:.2f}"
        )

    return (
        f"*{idx}.* {sig}  `{p.ticker}`\n"
        f"   {p.company_name}\n"
        f"   {risk}  |  conf {p.confidence:.0f}%\n"
        f"   📈 Move: {move}\n"
        f"   🛑 Stop %: {sl}"
        f"{price_lines}"
    )


def format_whatsapp_message(result: DailyPicksResult) -> str:
    sentiment_icon = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(
        result.overall_sentiment, "➡️"
    )
    events = ", ".join(e.replace("_", " ").title() for e in result.events_detected[:3]) or "None"

    lines = [
        f"🌐 *Geo-Stock Intraday Picks — {result.generated_for}*",
        f"{sentiment_icon} Sentiment: {result.overall_sentiment.title()}",
        f"📰 Events: {events}",
        f"⏰ Entry: 9:15 AM IST  |  Exit: Before 3:15 PM IST",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if result.no_picks_reason or not result.picks:
        lines.append(f"⚠️ No picks today: {result.no_picks_reason or 'No strong signals.'}")
    else:
        for i, pick in enumerate(result.picks, 1):
            lines.append(_format_pick(i, pick))
            lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 {result.news_count} articles analyzed",
        "⚠️ _AI signals only. Trade at your own risk._",
    ]
    return "\n".join(lines)


# ── CallMeBot ─────────────────────────────────────────────────────────────────

def send_via_callmebot(phone: str, api_key: str, message: str) -> tuple[bool, str]:
    """Send via CallMeBot (free, personal). Returns (success, error)."""
    try:
        r = requests.get(
            _CALLMEBOT_URL,
            params={"phone": phone, "text": message, "apikey": api_key},
            timeout=15,
        )
        if r.status_code == 200 and "Message Sent" in r.text:
            return True, ""
        return False, f"CallMeBot {r.status_code}: {r.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, str(e)


# ── Twilio ────────────────────────────────────────────────────────────────────

def send_via_twilio(
    phone: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
    message: str,
    timeout_sec: int = 20,
) -> tuple[bool, str]:
    """Send via Twilio WhatsApp sandbox/number. Returns (success, error)."""
    import concurrent.futures

    if not account_sid or not auth_token or not from_number or not phone:
        return False, "Missing credentials — fill in Account SID, Auth Token, From Number, and Phone."

    def _send() -> tuple[bool, str]:
        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            msg = client.messages.create(
                from_=f"whatsapp:{from_number}",
                body=message,
                to=f"whatsapp:{phone}",
            )
            return True, msg.sid
        except Exception as e:
            return False, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_send)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            return False, f"Request timed out after {timeout_sec}s. Check your credentials and network."


# ── Unified send (picks) ──────────────────────────────────────────────────────

def send_picks(
    result: DailyPicksResult,
    provider: str,          # "callmebot" | "twilio"
    phone: str,
    # CallMeBot
    callmebot_api_key: str = "",
    # Twilio
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    twilio_from_number: str = "",
) -> tuple[bool, str]:
    message = format_whatsapp_message(result)
    if provider == "twilio":
        return send_via_twilio(phone, twilio_account_sid, twilio_auth_token, twilio_from_number, message)
    return send_via_callmebot(phone, callmebot_api_key, message)


def send_test_message(
    provider: str,
    phone: str,
    callmebot_api_key: str = "",
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    twilio_from_number: str = "",
) -> tuple[bool, str]:
    msg = (
        "✅ *Geo-Stock Agent* — WhatsApp notifications are working!\n"
        "You'll receive daily intraday picks every morning before market open."
    )
    if provider == "twilio":
        return send_via_twilio(phone, twilio_account_sid, twilio_auth_token, twilio_from_number, msg)
    return send_via_callmebot(phone, callmebot_api_key, msg)
