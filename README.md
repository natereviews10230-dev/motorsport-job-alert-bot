# Motorsport Experience Job Alert Bot — GitHub Actions

Cloud-hosted career-site watcher for motorsport and Formula 1 employers. It sends an ntfy push notification when a newly detected opening matches finance, accounting, planning, strategy, commercial, systems, procurement, licensing, sponsorship, or closely related experience.

## Start here

Read **[GITHUB_SETUP_GUIDE.md](GITHUB_SETUP_GUIDE.md)**.

## Key behavior

- Runs every five minutes in the included public-repository workflow.
- Your laptop does not need to remain on.
- First run establishes the existing-job baseline without flooding notifications.
- `job_alerts.sqlite3` stores seen jobs and is committed only when state changes.
- Ford Global Finance and Ford Credit are removed.
- Ford monitoring is restricted to Ford Racing/Performance/motorsport postings.

## Local commands

Validate:

```bash
python job_watcher.py --config config.json --validate
```

Preview current matches without saving:

```bash
python job_watcher.py --config config.json --preview
```

Run one cloud-style check:

```bash
python job_watcher.py --config config.json --once
```
