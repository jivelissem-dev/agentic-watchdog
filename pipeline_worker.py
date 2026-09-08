"""
pipeline_worker.py

A small simulated "agentic" pipeline with three steps:
    fetch_data -> process_data -> write_output

Each step can fail in a controlled, reproducible way, driven by
failure_injection.json. This lets the watchdog demo show real
self-healing behavior (retry N, succeed on N+1) without depending
on flaky real-world APIs.

In a real deployment you'd replace these three functions with your
actual pipeline logic (API calls, LLM generation steps, file writes,
etc). The watchdog doesn't care what's inside a step -- it only
cares whether the step raises an exception.
"""

import json
import os
import time

STATE_FILE = os.path.join(os.path.dirname(__file__), "failure_injection.json")


class RateLimitError(Exception):
    """Simulates a 429 / rate-limited upstream API."""


class CorruptDataError(Exception):
    """Simulates malformed data that no automatic retry can fix."""


def _load_injection_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def _save_injection_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _maybe_fail(step_name):
    """
    Checks failure_injection.json for a rule like:
        "fetch_data": {"fail_times": 2, "attempts_so_far": 0, "exception": "ConnectionError"}

    Fails with the named exception until attempts_so_far reaches fail_times,
    then lets the step succeed. This simulates a transient bug that the
    watchdog's retries genuinely fix.
    """
    state = _load_injection_state()
    rule = state.get(step_name)
    if not rule:
        return  # no injected failure for this step

    if rule["attempts_so_far"] < rule["fail_times"]:
        rule["attempts_so_far"] += 1
        _save_injection_state(state)

        exc_name = rule["exception"]
        message = f"Simulated {exc_name} on '{step_name}' (attempt {rule['attempts_so_far']}/{rule['fail_times']})"

        if exc_name == "ConnectionError":
            raise ConnectionError(message)
        elif exc_name == "TimeoutError":
            raise TimeoutError(message)
        elif exc_name == "FileExistsError":
            raise FileExistsError(message)
        elif exc_name == "ValueError":
            raise ValueError(message)
        elif exc_name == "RateLimitError":
            raise RateLimitError(message)
        elif exc_name == "CorruptDataError":
            raise CorruptDataError(message)
        else:
            raise RuntimeError(message)


def fetch_data(ctx):
    _maybe_fail("fetch_data")
    time.sleep(0.1)
    ctx["raw_data"] = {"records": [1, 2, 3, 4, 5]}
    return ctx


def process_data(ctx):
    _maybe_fail("process_data")
    time.sleep(0.1)
    ctx["processed"] = [r * 2 for r in ctx["raw_data"]["records"]]
    return ctx


def write_output(ctx):
    _maybe_fail("write_output")
    time.sleep(0.1)
    out_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "last_output.json")
    with open(out_path, "w") as f:
        json.dump(ctx["processed"], f)
    ctx["output_path"] = out_path
    return ctx


STEPS = [
    ("fetch_data", fetch_data),
    ("process_data", process_data),
    ("write_output", write_output),
]
