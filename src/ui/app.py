import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src.agents import news_agent, analysis_agent, recommendation_agent, backtest_agent, daily_picks_agent
from src.data.db import get_session, RecommendationRun, StockRecommendationDB, init_db
from src.models.recommendations import StockRecommendation
from src.models.backtest import BacktestResult
from src.models.daily_picks import DailyPick, DailyPicksResult

COUNTRIES = {"India": "IN"}
SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
SENTIMENT_EMOJI = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}


def _signal_color(signal: str) -> str:
    return {"BUY": "green", "SELL": "red", "HOLD": "orange"}.get(signal, "gray")


def render_recommendations_table(recommendations: list[StockRecommendation]) -> None:
    if not recommendations:
        st.info("No strong recommendations generated from current news.")
        return

    rows = []
    for r in recommendations:
        rows.append({
            "Signal": f"{SIGNAL_EMOJI.get(r.signal, '')} {r.signal}",
            "Ticker": r.ticker,
            "Company": r.company_name,
            "Sector": r.sector.replace("_", " ").title(),
            "Confidence": f"{r.confidence:.0f}%",
            "Horizon": r.time_horizon.replace("_", " ").title(),
            "Reasoning": r.reasoning,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_sector_heatmap(analysis) -> None:
    if not analysis.events:
        return

    sector_scores: dict[str, float] = {}
    for event in analysis.events:
        for impact in event.affected_sectors:
            w = {"low": 0.4, "medium": 0.7, "high": 1.0}.get(impact.magnitude, 0.5)
            score = event.confidence * w * (1 if impact.direction == "positive" else -1)
            sector_scores[impact.sector] = sector_scores.get(impact.sector, 0) + score

    if not sector_scores:
        return

    sectors = list(sector_scores.keys())
    scores = [sector_scores[s] for s in sectors]
    colors = ["green" if s > 0 else "red" for s in scores]
    labels = [s.replace("_", " ").title() for s in sectors]

    fig = go.Figure(go.Bar(
        x=labels,
        y=scores,
        marker_color=colors,
        text=[f"{s:+.2f}" for s in scores],
        textposition="outside",
    ))
    fig.update_layout(
        title="Sector Impact Heatmap",
        xaxis_title="Sector",
        yaxis_title="Net Impact Score",
        height=350,
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


def tab_live_recommendations() -> None:
    st.header("Live Recommendations")
    country_name = st.selectbox("Select Country", list(COUNTRIES.keys()), key="live_country")
    country_code = COUNTRIES[country_name]

    if st.button("Analyze Today's News", type="primary"):
        with st.spinner("Fetching geo-political news..."):
            articles = news_agent.get_news(country_code, date.today(), live=True)

        st.subheader(f"News Articles Found: {len(articles)}")
        if articles:
            with st.expander("View News Headlines", expanded=False):
                for a in articles[:20]:
                    st.markdown(f"- **{a.title}** — *{a.source}*")

        with st.spinner("Analyzing with Claude AI..."):
            geo_analysis = analysis_agent.analyze_news(articles)

        sentiment = geo_analysis.overall_market_sentiment
        st.subheader(f"Market Sentiment: {SENTIMENT_EMOJI.get(sentiment, '')} {sentiment.title()}")

        if geo_analysis.events:
            st.subheader("Detected Geo-Political Events")
            for event in geo_analysis.events:
                with st.expander(f"{event.type.replace('_', ' ').title()} (confidence: {event.confidence:.0%})"):
                    st.write(event.description)
                    for impact in event.affected_sectors:
                        emoji = "🟢" if impact.direction == "positive" else "🔴"
                        st.write(f"{emoji} **{impact.sector}** — {impact.magnitude} {impact.direction}: {impact.reasoning}")

        if geo_analysis.key_risks:
            st.subheader("Key Risks")
            for risk in geo_analysis.key_risks:
                st.warning(risk)

        render_sector_heatmap(geo_analysis)

        with st.spinner("Generating stock recommendations..."):
            recommendations = recommendation_agent.generate_recommendations(geo_analysis)

        st.subheader(f"Stock Recommendations ({len(recommendations)} stocks)")
        render_recommendations_table(recommendations)


def tab_backtest() -> None:
    st.header("Backtest Mode")
    st.write("Select a past date to see what the agent would have recommended and how those stocks actually performed.")

    col1, col2 = st.columns(2)
    with col1:
        country_name = st.selectbox("Select Country", list(COUNTRIES.keys()), key="bt_country")
        country_code = COUNTRIES[country_name]
    with col2:
        max_date = date.today() - timedelta(days=7)
        min_date = date(2020, 1, 1)
        selected_date = st.date_input(
            "Select Analysis Date",
            value=date(2024, 10, 1),
            min_value=min_date,
            max_value=max_date,
            key="bt_date",
        )

    st.caption("💡 Best dates to test: 2024-02-01 (India Budget), 2024-05-20 (Election results), 2024-10-01 (West Asia tensions), 2025-04-07 (India-Pakistan escalation)")

    if st.button("Run Backtest", type="primary"):
        with st.spinner(f"Fetching news and running AI analysis for {selected_date.isoformat()}..."):
            result: BacktestResult = backtest_agent.run_backtest(country_code, selected_date)

        st.subheader(f"Results for {selected_date.isoformat()}")

        # ── No events detected: show explanation instead of blank metrics ──
        if not result.events_detected:
            if result.no_events_reason:
                st.warning(f"⚠️ {result.no_events_reason}")
            if result.sample_headlines:
                with st.expander(f"📰 {result.news_count} articles were fetched but contained no market-moving events"):
                    for h in result.sample_headlines:
                        st.write(f"- {h}")
            st.info("Try one of the suggested dates above, or pick a weekday near a known event.")
            return

        col1, col2, col3, col4 = st.columns(4)
        if result.metrics:
            m = result.metrics
            col1.metric("Hit Rate", f"{m.hit_rate_pct:.0f}%", help="% of correct BUY/SELL calls")
            col2.metric("Avg Return", f"{m.avg_return_pct:+.1f}%", help="Average return on all recommended stocks")
            nifty_str = f"{m.nifty50_return_pct:+.1f}%" if m.nifty50_return_pct is not None else "N/A"
            col3.metric("Nifty 50 Return", nifty_str, help="Benchmark return over same period")
            alpha_str = f"{m.alpha_vs_nifty_pct:+.1f}%" if m.alpha_vs_nifty_pct is not None else "N/A"
            col4.metric("Alpha", alpha_str, help="Outperformance vs Nifty 50")

        st.write(f"**News articles analyzed:** {result.news_count}")
        st.write(f"**Market Sentiment:** {SENTIMENT_EMOJI.get(result.overall_sentiment, '')} {result.overall_sentiment.title()}")
        if result.events_detected:
            st.write(f"**Events detected:** {', '.join(e.replace('_', ' ').title() for e in result.events_detected)}")

        if result.metrics and result.metrics.portfolio_value is not None:
            initial = sum(10_000 for s in result.stocks if s.signal == "BUY")
            st.info(
                f"💼 Portfolio Simulation: ₹{initial:,.0f} invested → "
                f"₹{result.metrics.portfolio_value:,.0f} "
                f"({'+' if result.metrics.portfolio_value > initial else ''}"
                f"{result.metrics.portfolio_value - initial:,.0f})"
            )

        if result.stocks:
            st.subheader("Stock Performance")
            rows = []
            for s in result.stocks:
                correct_icon = "✅" if s.correct_call else ("❌" if s.correct_call is False else "—")
                rows.append({
                    "Signal": f"{SIGNAL_EMOJI.get(s.signal, '')} {s.signal}",
                    "Ticker": s.ticker,
                    "Company": s.company_name,
                    "Sector": s.sector.replace("_", " ").title(),
                    "Confidence": f"{s.confidence:.0f}%",
                    "Entry Price": f"₹{s.entry_price:.2f}" if s.entry_price else "N/A",
                    "Current Price": f"₹{s.current_price:.2f}" if s.current_price else "N/A",
                    "Return": f"{s.return_pct:+.1f}%" if s.return_pct is not None else "N/A",
                    "Correct?": correct_icon,
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Return distribution chart
            evaluated = [s for s in result.stocks if s.return_pct is not None]
            if evaluated:
                fig = px.bar(
                    x=[s.ticker for s in evaluated],
                    y=[s.return_pct for s in evaluated],
                    color=[s.return_pct > 0 for s in evaluated],
                    color_discrete_map={True: "green", False: "red"},
                    title="Return % per Recommended Stock",
                    labels={"x": "Ticker", "y": "Return %", "color": "Positive"},
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)


def tab_history() -> None:
    st.header("Backtest History")
    init_db()
    session = get_session()
    try:
        runs = session.query(RecommendationRun).filter_by(is_backtest=True).order_by(
            RecommendationRun.created_at.desc()
        ).limit(50).all()

        if not runs:
            st.info("No backtest runs yet. Go to the Backtest tab to run one.")
            return

        run_rows = []
        for run in runs:
            recs = session.query(StockRecommendationDB).filter_by(run_id=run.id).all()
            evaluated = [r for r in recs if r.return_pct is not None]
            correct = sum(1 for r in evaluated if r.correct_call)
            hit_rate = round(correct / len(evaluated) * 100, 1) if evaluated else 0
            avg_return = round(sum(r.return_pct for r in evaluated) / len(evaluated), 2) if evaluated else 0

            run_rows.append({
                "Date": run.analysis_date,
                "Country": run.country,
                "Sentiment": f"{SENTIMENT_EMOJI.get(run.overall_sentiment or 'neutral', '')} {(run.overall_sentiment or 'neutral').title()}",
                "Events": ", ".join((run.key_events or [])[:3]),
                "Recommendations": len(recs),
                "Hit Rate": f"{hit_rate:.0f}%",
                "Avg Return": f"{avg_return:+.1f}%",
                "Run At": str(run.created_at)[:16],
            })

        df = pd.DataFrame(run_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if run_rows:
            hit_rates = [float(r["Hit Rate"].replace("%", "")) for r in run_rows]
            avg_returns = [float(r["Avg Return"].replace("%", "").replace("+", "")) for r in run_rows]
            col1, col2 = st.columns(2)
            col1.metric("Overall Avg Hit Rate", f"{sum(hit_rates)/len(hit_rates):.0f}%")
            col2.metric("Overall Avg Return", f"{sum(avg_returns)/len(avg_returns):+.1f}%")
    finally:
        session.close()


_RISK_COLOR = {"low": "🟢", "medium": "🟡", "high": "🔴"}
_RISK_BADGE = {"low": "LOW RISK", "medium": "MED RISK", "high": "HIGH RISK"}


def _render_pick_card(pick: DailyPick, idx: int) -> None:
    is_buy = pick.signal == "BUY"
    signal_icon = "🟢 BUY" if is_buy else "🔴 SELL / AVOID"
    risk_icon = _RISK_COLOR[pick.risk_level]
    risk_label = _RISK_BADGE[pick.risk_level]

    # Direction-aware labels
    if is_buy:
        ret_label = f"+{pick.expected_return_min:.1f}% → +{pick.expected_return_max:.1f}%"
        sl_label  = f"Cut if drops -{pick.stop_loss_pct:.1f}%"
    else:
        ret_label = f"-{pick.expected_return_min:.1f}% → -{pick.expected_return_max:.1f}% (expected decline)"
        sl_label  = f"Exit if rises +{pick.stop_loss_pct:.1f}%"

    with st.container(border=True):
        col_sig, col_name, col_risk, col_ret, col_sl = st.columns([1.4, 3, 1.5, 2.5, 2])
        col_sig.markdown(f"### {signal_icon}")
        col_name.markdown(f"**{pick.company_name}**  \n`{pick.ticker}` · {pick.sector.replace('_', ' ').title()}")
        col_risk.markdown(f"{risk_icon} **{risk_label}**")
        col_ret.markdown(f"**Expected move:** `{ret_label}`")
        col_sl.markdown(f"**Stop Loss:** `{sl_label}`")

        st.caption(f"Confidence: {pick.confidence:.0f}%   ·   Triggered by: {', '.join(pick.triggered_by)}")
        st.write(f"_{pick.reasoning[:200]}_")


def tab_daily_picks() -> None:
    st.header("Tomorrow's Intraday Picks")
    st.write("5 stocks to buy at market open and sell before close — same day trade.")

    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.info("📥 **Entry** — 9:15 AM IST\nMarket open")
    col_info2.warning("📤 **Exit** — Before 3:15 PM IST\nSame day, before close")
    col_info3.error("🛑 **Stop Loss** — Cut position immediately if stock hits stop-loss %")

    country_name = st.selectbox("Country", list(COUNTRIES.keys()), key="dp_country")
    country_code = COUNTRIES[country_name]

    if st.button("Generate Tomorrow's Picks", type="primary", use_container_width=True):
        with st.spinner("Fetching today's geo-political news and generating picks..."):
            result: DailyPicksResult = daily_picks_agent.generate_daily_picks(country_code)

        st.markdown(f"### Picks for **{result.generated_for}** (next trading day)")

        col_a, col_b = st.columns(2)
        col_a.metric("News articles analyzed", result.news_count)
        col_b.metric("Market Sentiment",
                     f"{SENTIMENT_EMOJI.get(result.overall_sentiment, '')} {result.overall_sentiment.title()}")

        if result.events_detected:
            st.write("**Events driving picks:** " +
                     " · ".join(e.replace("_", " ").title() for e in result.events_detected))

        if result.no_picks_reason:
            st.warning(f"⚠️ {result.no_picks_reason}")
            return

        if not result.picks:
            st.info("No strong intraday picks generated from today's news.")
            return

        st.divider()
        st.subheader(f"Top {len(result.picks)} Intraday Picks")

        for i, pick in enumerate(result.picks, 1):
            st.markdown(f"#### #{i}")
            _render_pick_card(pick, i)

        # Summary table for quick scanning
        st.divider()
        st.subheader("Quick Summary")
        rows = []
        for p in result.picks:
            is_buy = p.signal == "BUY"
            exp = (f"+{p.expected_return_min:.1f}% to +{p.expected_return_max:.1f}%"
                   if is_buy else
                   f"-{p.expected_return_min:.1f}% to -{p.expected_return_max:.1f}%")
            sl = (f"Cut at -{p.stop_loss_pct:.1f}%" if is_buy else f"Exit at +{p.stop_loss_pct:.1f}%")
            rows.append({
                "Signal": f"{SIGNAL_EMOJI.get(p.signal, '')} {p.signal}",
                "Ticker": p.ticker,
                "Company": p.company_name,
                "Risk": f"{_RISK_COLOR[p.risk_level]} {p.risk_level.upper()}",
                "Expected Move": exp,
                "Stop Loss": sl,
                "Confidence": f"{p.confidence:.0f}%",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.caption(
            "⚠️ **Disclaimer:** AI-generated signals based on geo-political news only. "
            "**SELL** = expected to fall — avoid buying or exit existing positions "
            "(short-selling requires F&O margin). "
            "Stop-loss is the % move against you at which you should exit to limit losses. "
            "Intraday trading carries significant risk. Never invest more than you can afford to lose."
        )


def tab_settings() -> None:
    import os
    from dotenv import load_dotenv, set_key
    from src.notifications.whatsapp_client import send_test_message

    load_dotenv()
    st.header("⚙️ WhatsApp Notifications")

    env_path = Path(__file__).parent.parent.parent / ".env"

    # ── Provider choice ──────────────────────────────────────────────────────
    provider = st.radio(
        "Choose WhatsApp provider",
        ["Twilio (recommended)", "CallMeBot (free)"],
        horizontal=True,
        key="wa_provider",
    )
    use_twilio = provider.startswith("Twilio")

    st.divider()

    phone = st.text_input(
        "Your WhatsApp number (with country code)",
        value=os.getenv("WHATSAPP_PHONE", ""),
        placeholder="+91XXXXXXXXXX",
        key="wa_phone",
    )

    if use_twilio:
        st.markdown("""
**Twilio setup (3 min, free trial — no credit card):**
1. Sign up at **twilio.com** → go to Console
2. Sidebar → **Messaging → Try it out → Send a WhatsApp message**
3. Copy the **sandbox number** (e.g. `+14155238886`) and **join code** (e.g. `join bright-tiger`)
4. Send the join code from YOUR WhatsApp to the sandbox number → you'll see "joined"
5. Copy your **Account SID** and **Auth Token** from the Console homepage
""")
        col1, col2 = st.columns(2)
        with col1:
            twilio_sid = st.text_input("Account SID", value=os.getenv("TWILIO_ACCOUNT_SID", ""),
                                       placeholder="ACxxxxxxxxxxxxxxxx", key="tw_sid")
        with col2:
            twilio_token = st.text_input("Auth Token", value=os.getenv("TWILIO_AUTH_TOKEN", ""),
                                         type="password", placeholder="your auth token", key="tw_token")
        twilio_from = st.text_input(
            "Twilio sandbox WhatsApp number",
            value=os.getenv("TWILIO_FROM_NUMBER", "+14155238886"),
            placeholder="+14155238886",
            key="tw_from",
        )
        callmebot_key = ""
    else:
        st.markdown("""
**CallMeBot setup (60 sec, completely free):**
1. Save **+34 644 59 76 57** in your WhatsApp contacts as *CallMeBot*
2. Send this EXACT text to that contact on WhatsApp:
   > `I allow callmebot to send me messages`
3. Wait up to 2 minutes — you'll receive your API key
4. If no reply after 5 min: restart WhatsApp and try again
""")
        callmebot_key = st.text_input(
            "CallMeBot API key (received via WhatsApp)",
            value=os.getenv("WHATSAPP_API_KEY", ""),
            placeholder="123456",
            type="password",
            key="wa_key",
        )
        twilio_sid = twilio_token = twilio_from = ""

    st.divider()
    col3, col4 = st.columns(2)
    with col3:
        hour = st.number_input("Daily send time — Hour (IST)", min_value=0, max_value=23,
                               value=int(os.getenv("SCHEDULE_HOUR_IST", "8")), key="wa_hour")
    with col4:
        minute = st.number_input("Minute", min_value=0, max_value=59,
                                 value=int(os.getenv("SCHEDULE_MINUTE_IST", "0")),
                                 step=15, key="wa_min")

    col_save, col_test = st.columns(2)

    with col_save:
        if st.button("💾 Save Settings", use_container_width=True):
            if env_path.exists():
                set_key(str(env_path), "WHATSAPP_PHONE", phone)
                set_key(str(env_path), "WHATSAPP_PROVIDER", "twilio" if use_twilio else "callmebot")
                set_key(str(env_path), "WHATSAPP_API_KEY", callmebot_key)
                set_key(str(env_path), "TWILIO_ACCOUNT_SID", twilio_sid)
                set_key(str(env_path), "TWILIO_AUTH_TOKEN", twilio_token)
                set_key(str(env_path), "TWILIO_FROM_NUMBER", twilio_from)
                set_key(str(env_path), "SCHEDULE_HOUR_IST", str(hour))
                set_key(str(env_path), "SCHEDULE_MINUTE_IST", str(minute))
                st.success(f"Saved! Picks will be sent daily at {hour:02d}:{minute:02d} IST")
            else:
                st.error(".env file not found.")

    with col_test:
        if st.button("📲 Send Test Message", type="primary", use_container_width=True):
            errors = []
            if not phone.strip():
                errors.append("WhatsApp phone number")
            if use_twilio:
                if not twilio_sid.strip():
                    errors.append("Twilio Account SID")
                if not twilio_token.strip():
                    errors.append("Twilio Auth Token")
                if not twilio_from.strip():
                    errors.append("Twilio From Number")
            else:
                if not callmebot_key.strip():
                    errors.append("CallMeBot API key")

            if errors:
                st.error(f"Please fill in: {', '.join(errors)}")
            else:
                with st.spinner("Sending… (timeout 20s)"):
                    ok, err = send_test_message(
                        provider="twilio" if use_twilio else "callmebot",
                        phone=phone.strip(),
                        callmebot_api_key=callmebot_key.strip(),
                        twilio_account_sid=twilio_sid.strip(),
                        twilio_auth_token=twilio_token.strip(),
                        twilio_from_number=twilio_from.strip(),
                    )
                if ok:
                    st.success(f"✅ Message sent to {phone}! Check your WhatsApp.")
                else:
                    st.error(f"Failed: {err}")

    st.divider()
    st.subheader("Start the Daily Scheduler")
    st.info(
        "The scheduler runs outside the browser. Open a **new terminal** in the project folder and run:\n\n"
        "```bash\npython3 run_scheduler.py\n```\n\n"
        f"Picks will be sent every day at **{hour:02d}:{minute:02d} IST** "
        "(before the 9:15 AM NSE open). Keep the terminal running in the background."
    )


def main() -> None:
    st.set_page_config(
        page_title="Geo-Political Stock Agent",
        page_icon="🌐",
        layout="wide",
    )
    st.title("🌐 Geo-Political Stock Recommendation Agent")
    st.caption("AI-powered stock recommendations based on geo-political news analysis")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 Tomorrow's Picks",
        "📡 Live Recommendations",
        "⏪ Backtest Mode",
        "📊 History",
        "⚙️ WhatsApp Setup",
    ])

    with tab1:
        tab_daily_picks()

    with tab2:
        tab_live_recommendations()

    with tab3:
        tab_backtest()

    with tab4:
        tab_history()

    with tab5:
        tab_settings()


if __name__ == "__main__":
    main()
