"""
playbook_manager.py

This is the "gets smarter over time" piece. playbook.json tracks, per
error signature, which remediations have been tried and how often they
succeeded. Each time the watchdog needs to pick a fix, it asks for the
remediation with the best success rate it hasn't already tried on this
incident. Each time a fix is applied, the outcome updates the score --
so over many runs the playbook converges on "what actually works" for
each kind of failure, without any manual tuning.

If an error signature has never been seen before, get_best_remediation
returns None and the watchdog falls back to llm_diagnosis.py to propose
a first guess, which then gets added to the playbook.
"""

import json
from pathlib import Path

PLAYBOOK_PATH = Path(__file__).parent / "playbook.json"


def load_playbook():
    if not PLAYBOOK_PATH.exists():
        return {}
    with open(PLAYBOOK_PATH, "r") as f:
        return json.load(f)


def save_playbook(playbook):
    with open(PLAYBOOK_PATH, "w") as f:
        json.dump(playbook, f, indent=2)


def _success_rate(entry):
    total = entry["successes"] + entry["failures"]
    if total == 0:
        return 0.5  # untried fixes get a neutral prior, not zero
    return entry["successes"] / total


def get_best_remediation(playbook, error_signature, exclude=None):
    exclude = exclude or set()
    entries = playbook.get(error_signature, {}).get("remediations", [])
    candidates = [e for e in entries if e["name"] not in exclude]
    if not candidates:
        return None
    candidates.sort(key=_success_rate, reverse=True)
    return candidates[0]["name"]


def record_outcome(playbook, error_signature, remediation_name, success):
    sig_entry = playbook.setdefault(error_signature, {"remediations": []})
    remediations = sig_entry["remediations"]

    existing = next((r for r in remediations if r["name"] == remediation_name), None)
    if existing is None:
        existing = {"name": remediation_name, "successes": 0, "failures": 0}
        remediations.append(existing)

    if success:
        existing["successes"] += 1
    else:
        existing["failures"] += 1

    save_playbook(playbook)
