# Agentic Watchdog

A self-healing, self-improving watchdog that supervises a Python pipeline,
diagnoses failures, applies fixes automatically, and escalates to a human
only when it genuinely can't recover — while getting better at recovering
on its own the more it runs.

## Why this exists

Most "automation" demos show the happy path. This one is built around the
part that actually matters in production and in interviews: **what happens
when a step fails.** This watchdog:

1. **Detects** failures at the step level (not just "the whole run crashed")
2. **Diagnoses** the failure type, using a known-fix playbook first and a
   local LLM (Ollama/Qwen) as a fallback for errors it's never seen
3. **Remediates** automatically — retry with backoff, clear a stale lock,
   wait out a rate limit, reset bad in-memory state
4. **Learns** — every fix attempt updates a success-rate score per error
   type, so the playbook gets smarter run over run without manual tuning
5. **Escalates** to Slack (or a local log if no webhook is configured)
   only when every known and suggested fix has failed — it never silently
   swallows an error or retries forever

Every attempt is written to a SQLite audit trail (`watchdog.db`), so you
can point to exact rows and say "here's what it tried, and why."

## Architecture

```
watchdog.py            <- orchestrator: runs steps, catches failures, drives healing
pipeline_worker.py      <- the thing being watched (3-step demo pipeline)
playbook_manager.py     <- loads/scores/saves playbook.json (the "gets smarter" part)
playbook.json           <- learned fix success rates per error type
remediation_actions.py  <- the actual fix functions (retry, backoff, clear lock, etc.)
llm_diagnosis.py        <- asks local Ollama/Qwen to guess a fix for unknown errors
notifier.py             <- Slack escalation (falls back to local log)
state_store.py          <- SQLite audit trail of every run/attempt/outcome
failure_injection.json  <- controls the demo's simulated failures (reproducible)
run_watchdog.ps1        <- Windows entry point / Task Scheduler target
```

**Flow for one step:** try → fail → classify error type → look up best
known fix (or ask the LLM if it's a new error type) → apply fix → retry →
record whether it worked → repeat up to 4 attempts → escalate if still
failing.

## Part 1 — Run it locally

### Prerequisites
- Python 3.10+ installed and on PATH
- PowerShell (built into Windows)
- (Optional) Ollama running locally with `qwen2.5:3b-instruct` pulled, if
  you want real LLM diagnosis instead of the heuristic fallback
- (Optional) A Slack Incoming Webhook URL, if you want real Slack alerts

### Steps

1. **Create the project folder and open it in PowerShell.**
   ```powershell
   mkdir C:\dev\agentic-watchdog
   cd C:\dev\agentic-watchdog
   ```

2. **Add all the files from this project** (pipeline_worker.py,
   watchdog.py, playbook_manager.py, remediation_actions.py,
   llm_diagnosis.py, notifier.py, state_store.py, failure_injection.json,
   playbook.json, requirements.txt, run_watchdog.ps1, .gitignore) into
   that folder.

3. **Create a virtual environment and install dependencies.**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. **Run the watchdog directly** to see the base demo (a transient
   connection error that clears after 2 retries, and a file-lock error
   that clears after 1 fix):
   ```powershell
   python watchdog.py
   ```
   You should see it fail, apply a remediation, retry, and eventually
   print `Run <id> completed successfully.`

5. **Run it again.** Open `playbook.json` — you'll see success/failure
   counts for `retry_with_backoff` and `clear_temp_lock`. This file is
   the proof that the system is learning: as you run more scenarios,
   the watchdog starts picking the historically-best fix first instead
   of guessing.

6. **Trigger an escalation** to see the other half of the system. Edit
   `failure_injection.json` to:
   ```json
   {
     "process_data": {
       "exception": "CorruptDataError",
       "fail_times": 99,
       "attempts_so_far": 0
     }
   }
   ```
   Run `python watchdog.py` again. It fails immediately and correctly
   with no known fix — check `logs\escalations.log` for the alert.
   Revert `failure_injection.json` afterward (or delete it and see the
   pipeline run clean with zero injected failures).

7. **Inspect the audit trail:**
   ```powershell
   python -c "import sqlite3; c=sqlite3.connect('watchdog.db'); [print(r) for r in c.execute('SELECT * FROM events')]"
   ```

## Part 2 — Wire in the real integrations

**Real Slack alerts:** create an Incoming Webhook in your Slack workspace
(Slack App settings → Incoming Webhooks → Add New Webhook), then:
```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
python watchdog.py
```

**Real local LLM diagnosis:** with Ollama running and `qwen2.5:3b-instruct`
pulled (`ollama pull qwen2.5:3b-instruct`), no changes needed —
`llm_diagnosis.py` already targets `http://localhost:11434` by default.
Delete an error type from `playbook.json` and re-run to see it ask the
model for a fresh guess instead of using the heuristic fallback.

**Point it at a real pipeline instead of the demo:** replace the three
functions in `pipeline_worker.py` with your actual logic (API calls, file
processing, whatever). The watchdog doesn't care what's inside a step —
it only needs each step to be a function that raises on failure.

## Part 3 — Schedule it (Windows Task Scheduler)

1. Open **Task Scheduler** → **Create Task** (not "Basic Task" — you want
   the full dialog).
2. **General tab:** name it `Agentic Watchdog`, select "Run whether user
   is logged on or not."
3. **Triggers tab → New:** set it to your desired cadence (e.g. Daily,
   repeat every 15 minutes for a long-running duration).
4. **Actions tab → New:**
   - Action: `Start a program`
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\dev\agentic-watchdog\run_watchdog.ps1"`
5. **Conditions/Settings tabs:** uncheck "Start the task only if the
   computer is on AC power" if this runs on a laptop.
6. Click OK, then right-click the task → **Run** to test it immediately.
   Check `logs\watchdog_run_<date>.log`.

## Part 4 — Publish to GitHub

1. **Initialize the repo** (from inside the project folder):
   ```powershell
   git init
   git add .
   git commit -m "Initial commit: self-healing agentic pipeline watchdog"
   ```
2. **Create the repo on GitHub:** go to github.com → New repository →
   name it `agentic-watchdog` → do NOT initialize with a README (you
   already have one) → Create repository.
3. **Push it:**
   ```powershell
   git remote add origin https://github.com/<your-username>/agentic-watchdog.git
   git branch -M main
   git push -u origin main
   ```
4. **Make the commit history tell a story.** Instead of one giant commit,
   consider re-doing this in a few logical commits if you have time:
   pipeline skeleton → remediation logic → learning/playbook →
   LLM fallback → Slack escalation → PowerShell scheduler. A reviewer
   skimming your commit log should be able to see the system get built
   up in a sensible order — that's a signal in itself.
5. **Add topics/tags on the GitHub repo page:** `python`, `automation`,
   `agentic-ai`, `self-healing`, `sre`, `ollama` — these help it surface
   in searches recruiters or engineers might run.

## How to talk about this in an interview or resume

**Resume bullet:**
> Built a self-healing Python watchdog that supervises pipeline execution,
> automatically diagnoses and remediates failures (retry/backoff, stale
> lock clearing, rate-limit handling), and escalates unresolvable errors —
> with a learning playbook that improves fix selection over time based on
> historical success rates.

**If asked "walk me through it":** lead with the failure story, not the
code — "the pipeline hits a transient error, the watchdog classifies it,
checks what's worked before, applies that fix, and only pages a human if
nothing works." Then point to `playbook.json` and the SQLite audit trail
as the proof it's not just retry-blindly logic.
