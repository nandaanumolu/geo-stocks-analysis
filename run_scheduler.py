"""
Daily scheduler: generates intraday picks at 8:00 AM IST and sends to WhatsApp.
Exposes a lightweight HTTP health-check on $PORT so Render web service stays alive.
"""
import sys
import logging
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from src.agents.daily_picks_agent import generate_daily_picks, generate_eod_report
from src.agents.post_mortem_agent import run_post_mortem
from src.notifications.webhook_client import send_daily_picks, send_eod_report

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

N8N_WEBHOOK_URL     = os.getenv("N8N_WEBHOOK_URL", "")
SCHEDULE_HOUR       = int(os.getenv("SCHEDULE_HOUR_IST", "8"))
SCHEDULE_MINUTE     = int(os.getenv("SCHEDULE_MINUTE_IST", "0"))
PORT                = int(os.getenv("PORT", "8080"))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/trigger":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Triggered! Check Render logs for progress.")
            threading.Thread(target=job_generate_and_send, daemon=True).start()
        elif self.path == "/trigger-eod":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"EOD report triggered! Check Render logs for progress.")
            threading.Thread(target=job_eod_report, daemon=True).start()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # suppress HTTP access logs


def job_generate_and_send() -> None:
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    log.info(f"Running daily picks job at {now}")

    if not N8N_WEBHOOK_URL:
        log.error("N8N_WEBHOOK_URL not set — cannot send.")
        return

    try:
        log.info("Generating intraday picks for India...")
        result = generate_daily_picks("IN")
        log.info(f"Generated {len(result.picks)} picks for {result.generated_for}")

        ok, err = send_daily_picks(N8N_WEBHOOK_URL, result)
        if ok:
            log.info("Daily picks sent to n8n webhook successfully")
        else:
            log.error(f"Webhook send failed: {err}")
    except Exception as e:
        log.exception(f"Daily picks job failed: {e}")


def job_eod_report() -> None:
    trade_date = datetime.now(IST).strftime("%Y-%m-%d")
    log.info(f"Running EOD report for {trade_date}")

    if not N8N_WEBHOOK_URL:
        log.error("N8N_WEBHOOK_URL not set — cannot send.")
        return

    report = generate_eod_report(trade_date)

    post_mortem_text = ""
    try:
        log.info("Running post-mortem analysis...")
        post_mortem_text = run_post_mortem(trade_date) or ""
        log.info("Post-mortem analysis complete")
    except Exception as e:
        log.exception(f"Post-mortem failed (non-fatal): {e}")

    ok, err = send_eod_report(N8N_WEBHOOK_URL, report, trade_date, post_mortem=post_mortem_text)
    if ok:
        log.info("EOD report sent to n8n webhook successfully")
    else:
        log.error(f"EOD report webhook send failed: {err}")


def main() -> None:
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(
        job_generate_and_send,
        trigger="cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="daily_picks",
        name=f"Daily picks at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} IST",
    )
    scheduler.add_job(
        job_eod_report,
        trigger="cron",
        hour=15,
        minute=30,
        id="eod_report",
        name="EOD performance report at 15:30 IST",
    )
    scheduler.start()

    next_run = scheduler.get_jobs()[0].next_run_time
    log.info(f"Scheduler started — next run at {next_run.strftime('%Y-%m-%d %H:%M IST')}")
    log.info(f"Webhook: {N8N_WEBHOOK_URL or '(not configured)'}")
    log.info(f"Health-check server on port {PORT}")

    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        scheduler.shutdown()
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
