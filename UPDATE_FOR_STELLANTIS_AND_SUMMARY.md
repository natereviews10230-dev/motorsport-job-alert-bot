# Update: Stellantis Auburn Hills + One ntfy Summary Per Run

This update adds Stellantis and changes ntfy delivery to one consolidated message per GitHub Actions run.

## What changed

- Stellantis official careers search is monitored through a headless browser because its public search results are JavaScript-rendered.
- Stellantis is restricted to **Auburn Hills, Michigan**.
- Stellantis uses the existing finance/accounting/strategy/business filters **plus** merchandising and licensed-product title terms. Existing global `licensing` matching remains active.
- The first successful Stellantis run treats matching Stellantis positions as new so you can verify the end-to-end alert path.
- ntfy now sends **one consolidated notification per run** listing every current match. New jobs are marked `🆕`.
- A clickable `current_matches.md` report is generated with direct application links. Tapping the ntfy notification opens that report once GitHub has committed the run state.
- New jobs are not recorded as seen if the required ntfy summary fails, so a notification outage does not silently lose an alert.
- GitHub Actions dependencies were updated to `actions/checkout@v6` and `actions/setup-python@v6` to remove the Node 20 warning.

## Important: notification frequency

The workflow is changed to every **6 minutes**, so `summary_mode: every_run` produces up to **240 ntfy notifications per day**. The six-minute cadence is intentional because ntfy.sh documents a default 250-message/day limit. This is still extremely noisy and is intended only for your verification period.

After you confirm it is reliable, change in `config.json`:

```json
"summary_mode": "every_run"
```

to a less noisy mode in a future update, or ask ChatGPT to change the workflow cadence.

## Files to replace on GitHub

Replace these repository files with the versions in this update package:

1. `job_watcher.py`
2. `config.json`
3. `requirements.txt`
4. `.github/workflows/motorsport-job-watcher.yml` — use the contents of `.github/workflows/job-alert.yml` from this package if your repository workflow has this manual name.

Do **not** keep two active workflow YAML files with the same schedule. If your repository already uses `.github/workflows/motorsport-job-watcher.yml`, update that file and do not also add `job-alert.yml`.

## Test it

1. Commit the replaced files.
2. Open **Actions → Motorsport Job Watcher**.
3. Click **Run workflow**.
4. The job log should include a line similar to:

```text
Stellantis - Auburn Hills: fetched X jobs; Y matched
```

5. You should receive **one ntfy notification** for the run. Any first-run Stellantis matches should have `🆕`.
6. On the next run, the same Stellantis jobs should still appear in the current list but should no longer have the `🆕` marker.

If Stellantis shows `fetched 0 jobs`, send the Stellantis section of the GitHub Actions log back to ChatGPT. The careers page is dynamically rendered and may occasionally change its HTML/pagination controls.
