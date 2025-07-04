# pipeline_utils/notification_utils.py

import os
import logging
import requests
import smtplib
from email.message import EmailMessage

# -------- ENV VARS --------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
NOTIFY_EMAILS = os.environ.get("NOTIFY_EMAILS")
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

# Configure logging
logger = logging.getLogger("notification_utils")

def send_telegram_message(message):
    """Send a notification message via Telegram."""
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            resp = requests.post(url, data=data, timeout=5)
            if not resp.ok:
                logger.warning(f"Telegram notification failed: {resp.text}")
        except Exception as e:
            logger.warning(f"Telegram notification error: {e}")
    else:
        logger.debug("Telegram notification skipped (missing credentials)")

def send_slack_message(message):
    """Send a notification message via Slack webhook."""
    if SLACK_WEBHOOK_URL:
        try:
            resp = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
            if not resp.ok:
                logger.warning(f"Slack notification failed: {resp.text}")
        except Exception as e:
            logger.warning(f"Slack notification error: {e}")
    else:
        logger.debug("Slack notification skipped (missing webhook URL)")

def send_email(subject, message):
    """Send a notification email."""
    if NOTIFY_EMAILS and SMTP_SERVER and SMTP_USERNAME and SMTP_PASSWORD:
        try:
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = subject
            msg["From"] = SMTP_USERNAME
            msg["To"] = [e.strip() for e in NOTIFY_EMAILS.split(",")]
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            logger.warning(f"Email notification error: {e}")
    else:
        logger.debug("Email notification skipped (missing credentials)")

def notify_all(subject, message):
    """Send a notification to all configured channels."""
    send_telegram_message(message)
    send_slack_message(message)
    send_email(subject, message)
