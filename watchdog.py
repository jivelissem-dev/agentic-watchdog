"""
watchdog.py

The orchestrator. Runs each step of pipeline_worker.STEPS. When a step
raises, it:

  1. classifies the failure (exception type = "error signature")
  2. asks playbook_manager for the best-known fix for that signature
     that hasn't already been tried on this incident
  3. if the signature has never been seen, asks llm_diagnosis for a
     first guess instead
  4. applies the remediation and retries the SAME step (not the whole
     pipeline) up to MAX_ATTEMPTS times
  5. records whether that remediation worked, so the playbook's success
     rates improve run over run
  6. if every option is exhausted, escalates to a human via notifier
     and stops the run -- it never silently drops a failure

Every attempt, remediation, and outcome is written to watchdog.db via
state_store, so you get a full audit trail of what the agent tried and
why -- which is the part that actually matters in an interview.
"""

import sys

import notifier
import playbook_manager
import state_store
from llm_diagnosis import diagnose_unknown_error
from pipeline_worker import STEPS
from remediation_actions import REMEDIATIONS

MAX_ATTEMPTS_PER_STEP = 4


def run_step_with_healing(run_id, step_name, step_fn, ctx, playbook):
    tried_this_incident = set()
    last_remediation = None
    last_signature = None

    for attempt in range(1, MAX_ATTEMPTS_PER_STEP + 1):
        try:
            step_fn(ctx)

            # Step succeeded -- if a remediation was applied just before
            # this attempt, that remediation gets credit.
            if last_remediation:
                playbook_manager.record_outcome(
                    playbook, last_signature, last_remediation, success=True
                )
            state_store.log_event(run_id, step_name, "success")
            print(f"  ✅ {step_name} succeeded (attempt {attempt})")
            return True

        except Exception as e:
            signature = type(e).__name__
            print(f"  ⚠️  {step_name} failed on attempt {attempt}: {signature}: {e}")
            state_store.log_event(
                run_id, step_name, "failure", error_signature=signature
            )

            # The previous remediation didn't fix it -- record that too.
            if last_remediation:
                playbook_manager.record_outcome(
                    playbook, last_signature, last_remediation, success=False
                )
                tried_this_incident.add(last_remediation)

            remediation_name = playbook_manager.get_best_remediation(
                playbook, signature, exclude=tried_this_incident
            )

            if remediation_name is None:
                remediation_name = diagnose_unknown_error(signature, str(e))
                if remediation_name is None:
                    # Neither the playbook nor the LLM has a plausible fix.
                    state_store.log_event(
                        run_id, step_name, "escalation",
                        error_signature=signature, outcome="no_known_fix",
                    )
                    notifier.send_slack_alert(
                        f"Run {run_id}: step '{step_name}' failed with "
                        f"{signature} and no known or suggested fix exists. "
                        f"Needs human review."
                    )
                    return False

            remediation_fn = REMEDIATIONS[remediation_name]
            print(f"  🔧 applying remediation: {remediation_name}")
            state_store.log_event(
                run_id, step_name, "remediation_applied",
                error_signature=signature, remediation_tried=remediation_name,
            )
            remediation_fn(ctx, attempt)

            last_remediation = remediation_name
            last_signature = signature

    # Exhausted all attempts for this step.
    state_store.log_event(
        run_id, step_name, "escalation",
        error_signature=last_signature, outcome="max_attempts_exhausted",
    )
    notifier.send_slack_alert(
        f"Run {run_id}: step '{step_name}' still failing after "
        f"{MAX_ATTEMPTS_PER_STEP} attempts and every known remediation. "
        f"Needs human review."
    )
    return False


def main():
    state_store.init_db()
    playbook = playbook_manager.load_playbook()

    run_id = state_store.start_run()
    print(f"Starting run {run_id}")

    ctx = {}
    for step_name, step_fn in STEPS:
        ok = run_step_with_healing(run_id, step_name, step_fn, ctx, playbook)
        if not ok:
            state_store.end_run(run_id, "Escalated")
            print(f"Run {run_id} ESCALATED at step '{step_name}'.")
            sys.exit(1)

    state_store.end_run(run_id, "Completed")
    print(f"Run {run_id} completed successfully. Output: {ctx.get('output_path')}")


if __name__ == "__main__":
    main()
