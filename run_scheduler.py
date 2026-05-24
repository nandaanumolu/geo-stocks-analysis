"""
Daily scheduler: generates intraday picks at 8:00 AM IST and sends to WhatsApp.

Usage:
    python3 run_scheduler.py

Reads WHATSAPP_PHONE and WHATSAPP_API_KEY from .env
"""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import os
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from src.agents.daily_picks_agent import generate_daily_picks
from src.notifications.whatsapp_client import send_picks

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

WHATSAPP_PHONE      = os.getenv("WHATSAPP_PHONE", "")
WHATSAPP_PROVIDER   = os.getenv("WHATSAPP_PROVIDER", "callmebot")   # "callmebot" | "twilio"
WHATSAPP_API_KEY    = os.getenv("WHATSAPP_API_KEY", "")              # CallMeBot key
TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "")
SCHEDULE_HOUR       = int(os.getenv("SCHEDULE_HOUR_IST", "8"))
SCHEDULE_MINUTE     = int(os.getenv("SCHEDULE_MINUTE_IST", "0"))


def job_generate_and_send() -> None:
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    log.info(f"Running daily picks job at {now} via {WHATSAPP_PROVIDER}")

    if not WHATSAPP_PHONE:
        log.error("WHATSAPP_PHONE not set in .env — cannot send.")
        return

    try:
        log.info("Generating intraday picks for India...")
        result = generate_daily_picks("IN")
        log.info(f"Generated {len(result.picks)} picks for {result.generated_for}")

        ok, err = send_picks(
            result,
            provider=WHATSAPP_PROVIDER,
            phone=WHATSAPP_PHONE,
            callmebot_api_key=WHATSAPP_API_KEY,
            twilio_account_sid=TWILIO_ACCOUNT_SID,
            twilio_auth_token=TWILIO_AUTH_TOKEN,
            twilio_from_number=TWILIO_FROM_NUMBER,
        )
        if ok:
            log.info(f"WhatsApp sent successfully to {WHATSAPP_PHONE}")
        else:
            log.error(f"WhatsApp send failed: {err}")
    except Exception as e:
        log.exception(f"Daily picks job failed: {e}")


def main() -> None:
    if not WHATSAPP_PHONE or not WHATSAPP_API_KEY:
        print("\n⚠️  WHATSAPP_PHONE and WHATSAPP_API_KEY are not set in your .env file.")
        print("    Add them and restart.\n")

    scheduler = BlockingScheduler(timezone=IST)
    scheduler.add_job(
        job_generate_and_send,
        trigger="cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="daily_picks",
        name=f"Daily picks at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} IST",
    )

    next_run = scheduler.get_jobs()[0].next_run_time
    print(f"\n✅ Scheduler started.")
    print(f"   Picks will be sent every day at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} IST")
    print(f"   Next run: {next_run.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"   WhatsApp: {WHATSAPP_PHONE or '(not configured)'}")
    print(f"\n   Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


if __name__ == "__main__":
    main()
