"""
remediation_actions.py

Each function here is a "fix" the watchdog can apply after a step fails.
They're referenced by name from playbook.json, so adding a new fix is:
  1. write the function here
  2. add its name to the relevant error signature's remediation list

Every action must accept (ctx, attempt) and may mutate ctx or sleep,
but should never raise -- a remediation that itself throws is treated
as a failed remediation attempt by the watchdog.
"""

import os
import time


def retry_immediately(ctx, attempt):
    """No real fix -- just try again right away. Good first guess for flukes."""
    return


def retry_with_backoff(ctx, attempt):
    """Exponential backoff: 1s, 2s, 4s... Good for transient network errors."""
    wait = min(2 ** attempt, 30)
    time.sleep(wait)


def wait_for_rate_limit(ctx, attempt):
    """Fixed cooldown, appropriate for 429 / rate-limit style errors."""
    time.sleep(3)


def clear_temp_lock(ctx, attempt):
    """Removes a stale lock/temp file that's blocking a file-based step."""
    lock_path = os.path.join(os.path.dirname(__file__), "logs", ".lock")
    if os.path.exists(lock_path):
        os.remove(lock_path)


def restart_worker_state(ctx, attempt):
    """Resets in-memory context, in case bad state carried over between attempts."""
    for key in ("raw_data", "processed"):
        ctx.pop(key, None)


REMEDIATIONS = {
    "retry_immediately": retry_immediately,
    "retry_with_backoff": retry_with_backoff,
    "wait_for_rate_limit": wait_for_rate_limit,
    "clear_temp_lock": clear_temp_lock,
    "restart_worker_state": restart_worker_state,
}
