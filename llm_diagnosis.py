"""
llm_diagnosis.py

Called only when the watchdog hits an error signature that isn't in
playbook.json yet -- i.e. something it has never seen before. This is
the "agentic reasoning" step: instead of giving up immediately, it asks
an LLM (your local Ollama/Qwen setup) to suggest which known remediation
is most likely to help, based on the exception type and message.

On a machine without Ollama running, this silently falls back to a
keyword heuristic so the demo still works. On your dev machine, set
OLLAMA_HOST (defaults to http://localhost:11434) and it will use your
local qwen2.5 model for real.
"""

import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct")

KNOWN_REMEDIATIONS = [
    "retry_immediately",
    "retry_with_backoff",
    "wait_for_rate_limit",
    "clear_temp_lock",
    "restart_worker_state",
]


def _heuristic_guess(error_signature, error_message):
    msg = (error_message or "").lower()
    if "rate" in msg or error_signature == "RateLimitError":
        return "wait_for_rate_limit"
    if "lock" in msg or "exists" in msg or error_signature == "FileExistsError":
        return "clear_temp_lock"
    if "timeout" in msg or "connection" in msg or error_signature in (
        "ConnectionError", "TimeoutError",
    ):
        return "retry_with_backoff"
    if "corrupt" in msg or "malformed" in msg:
        return None  # nothing in the playbook can fix bad data -- escalate
    return "retry_immediately"


def diagnose_unknown_error(error_signature, error_message):
    """
    Returns a remediation name to try, or None if this looks unfixable
    by the known playbook (in which case the watchdog escalates straight
    to a human instead of burning retries).
    """
    prompt = (
        "A Python pipeline step failed with this error:\n"
        f"Type: {error_signature}\nMessage: {error_message}\n\n"
        f"Known fixes available: {', '.join(KNOWN_REMEDIATIONS)}.\n"
        "Reply with exactly one fix name from that list, or the word NONE "
        "if none of them would plausibly help."
    )

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=5,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        for name in KNOWN_REMEDIATIONS:
            if name in answer:
                return name
        if "NONE" in answer.upper():
            return None
    except requests.exceptions.RequestException:
        pass  # Ollama not reachable -- fall back to heuristic below

    return _heuristic_guess(error_signature, error_message)
