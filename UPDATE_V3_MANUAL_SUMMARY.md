# V3 update: quiet scheduled alerts + manual current-job summary

This version implements the requested behavior:

- Scheduled GitHub checks run every **5 minutes**.
- If no new matching job is found, **no ntfy notification is sent**.
- If one or more new matching jobs are found, **one consolidated ntfy notification** lists the new jobs.
- A manual **Run workflow** sends **one consolidated summary of every current match**.
- A GitHub **Re-run** (`run_attempt > 1`) also sends the full current summary.
- If the state database is missing (first deployment/reset), the run sends the full current summary.
- Manual summaries do **not** reset seen/new state.

## Stellantis

Stellantis is restricted to **Auburn Hills, Michigan** and matches the existing finance/accounting/strategy families plus licensing and merchandising-related titles, including accessory-product roles.

## Files to replace in the GitHub repository

1. `job_watcher.py`
2. `config.json`
3. `requirements.txt`
4. `.github/workflows/motorsport-job-watcher.yml`
5. Optional: `test_job_watcher.py`

Do not keep a second duplicate workflow YAML file in `.github/workflows/`.

## Test

After committing the files:

1. Open **Actions → Motorsport Job Watcher**.
2. Click **Run workflow**.
3. That manual run should send one ntfy message showing every current matching role.
4. The next ordinary scheduled run should remain silent unless a new matching job appears.

The full clickable list is also maintained in `current_matches.md`.
