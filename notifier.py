"""
notifier.py

Sends an escalation alert when the watchdog exhausts every known and
LLM-suggested remediation for a failure. Uses a Slack Incoming Webhook
if SLACK_WEBHOOK_URL is set; otherwise logs loudly to the console and
to logs/escalations.log, so the demo still "escalates" visibly without
requiring a Slack workspace.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import requests

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ESCALATION_LOG = Path(__file__).parent / "logs" / "escalations.log"


def send_slack_alert(message):
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] ESCALATION: {message}\n"

    ESCALATION_LOG.parent.mkdir(exist_ok=True)
    with open(ESCALATION_LOG, "a") as f:
        f.write(line)

    if not SLACK_WEBHOOK_URL:
        print(f"\n🚨 {line.strip()}  (no SLACK_WEBHOOK_URL set -- logged locally only)\n")
        return

    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": f"🚨 {message}"}, timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"Slack alert failed to send ({e}); see {ESCALATION_LOG}")
