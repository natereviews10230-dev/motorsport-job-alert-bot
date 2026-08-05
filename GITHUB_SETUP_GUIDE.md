# GitHub Actions Setup Guide — Motorsport Job Alerts

This version runs in GitHub's cloud, so your laptop does **not** need to stay on. It checks the target career sites, remembers jobs it has already seen, and sends an ntfy push notification only for a newly detected matching role.

## What changed from the laptop version

- Removed **Ford Global Finance**.
- Removed **Ford Credit Services**.
- Added **Ford Racing only**, using Ford's official Oracle Recruiting career system and then requiring the posting to mention Ford Racing, Ford Performance, motorsport, or motorsports.
- Expanded matching to cover finance/accounting plus close matches to your experience, such as business planning, program finance, strategy, commercial analysis, financial systems, consolidation, program-management analysis, procurement, licensing, sponsorship, and partnerships.
- Converted the script to a one-check-per-run design for GitHub Actions.
- Added persistent seen-job history, so the same posting is not repeatedly sent.
- Added a monthly heartbeat commit so a public scheduled workflow does not become inactive after a long period with no new jobs.

## Recommended setup

Use a **public GitHub repository** and the included five-minute schedule.

Why public: standard GitHub-hosted runners are free for public repositories. A private GitHub Free repository receives 2,000 Actions minutes per month; checking every five minutes would normally exceed that allowance because each job is rounded up to a whole minute.

What becomes public: the bot code, company source configuration, and the titles/links stored in the seen-job database.

What stays private: your ntfy topic is stored as a GitHub Actions secret and is not written into the repository.

For a private repository, change the schedule to every 30 minutes as explained under **Private repository schedule**.

---

# Part 1 — Prepare the folder

1. Download and extract the supplied ZIP.
2. Open the extracted `motorsport_job_alert_github` folder.
3. Optional but recommended: copy your existing local state file:

   ```text
   C:\JobBot\job_alerts.sqlite3
   ```

   into the extracted folder, replacing any file with the same name.

   This preserves jobs your laptop bot already marked as seen. Old Ford Global/Ford Credit records are harmless; those sources are no longer checked.

4. Confirm the folder contains:

   ```text
   .github\workflows\job-alert.yml
   .state\heartbeat.txt
   config.json
   job_watcher.py
   requirements.txt
   GITHUB_SETUP_GUIDE.md
   ```

Windows may not display file extensions unless **View → Show → File name extensions** is enabled.

---

# Part 2 — Create the GitHub repository

1. Sign in at `https://github.com`.
2. Click the **+** button in the upper-right corner.
3. Select **New repository**.
4. Repository name:

   ```text
   motorsport-job-alert-bot
   ```

5. Select **Public** for the free five-minute schedule.
6. Do **not** add a README, `.gitignore`, or license; those files are already included.
7. Click **Create repository**.

---

# Part 3 — Upload the bot

On the new empty repository page:

1. Click **uploading an existing file**.
2. Open the extracted folder on your computer.
3. Select and drag the **contents inside the folder** onto GitHub—not the outer folder itself.
4. Make sure the upload includes the `.github` folder. The workflow must ultimately appear at:

   ```text
   .github/workflows/job-alert.yml
   ```

5. In the commit box, enter:

   ```text
   Add motorsport job watcher
   ```

6. Click **Commit changes**.

### If the browser will not upload the `.github` folder

Upload the other files first. Then:

1. Click **Add file → Create new file**.
2. For the file name, type:

   ```text
   .github/workflows/job-alert.yml
   ```

3. Copy the complete contents of the local `job-alert.yml` file into the editor.
4. Commit the new file.

---

# Part 4 — Add the ntfy secret

1. In the repository, click **Settings**.
2. In the left sidebar, select **Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Name:

   ```text
   NTFY_TOPIC
   ```

5. Secret value—use the exact ntfy topic already working on your phone:

   ```text
   nate-f1-finance-jobs-8x42k7p9
   ```

6. Click **Add secret**.

Do not place the topic directly in `config.json` or the workflow file.

### Optional authenticated ntfy account

Only when you use an authenticated ntfy server, add another repository secret:

```text
NTFY_TOKEN
```

For the normal public `ntfy.sh` topic you tested, this is not required.

---

# Part 5 — Allow the workflow to save its seen-job database

The bot must write `job_alerts.sqlite3` back to the repository when it sees new jobs.

1. Open **Settings → Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

The workflow itself also requests only `contents: write` permission.

---

# Part 6 — Run the first cloud test

1. Open the repository's **Actions** tab.
2. If prompted, click **I understand my workflows, go ahead and enable them**.
3. In the left sidebar, select **Motorsport Job Watcher**.
4. Click **Run workflow**.
5. Leave **Send an ntfy test notification** checked.
6. Click the green **Run workflow** button.
7. Refresh the page after a few seconds and open the new workflow run.

You should receive an ntfy message saying:

```text
Motorsport Job Bot is online
```

The job-check portion then runs once.

## What the first run does

- Existing matching jobs become the baseline.
- Existing jobs normally do **not** produce job alerts.
- New matching jobs detected on later runs do produce alerts.
- The workflow commits `job_alerts.sqlite3` to preserve the baseline.

A successful run appears with a green checkmark.

---

# Part 7 — Confirm automatic scheduling

The supplied public-repository workflow uses:

```yaml
- cron: "2/5 * * * *"
```

That requests a run every five minutes at minutes 2, 7, 12, 17, and so on. It is intentionally offset from the top of the hour, when GitHub scheduling load can be higher.

GitHub's five-minute schedule is not a guaranteed real-time service. Runs can occasionally start late, and under high load a scheduled run can be dropped. In normal operation, expect detection within roughly one scheduled interval plus the time needed to check the sites.

Your laptop can now be shut down. GitHub runs the checks independently.

---

# Private repository schedule

A private GitHub Free repository receives 2,000 Actions minutes per month. Since each workflow job is rounded up to at least one minute:

- Every 5 minutes: about 8,640 runs in a 30-day month — too many for the free private allowance.
- Every 15 minutes: about 2,880 runs — still above the free allowance.
- Every 30 minutes: about 1,440 runs — generally within the 2,000-minute allowance if no other Actions use consumes the account quota.

To use a private repository, edit `.github/workflows/job-alert.yml` and replace:

```yaml
- cron: "2/5 * * * *"
```

with:

```yaml
- cron: "7,37 * * * *"
```

That runs at 7 and 37 minutes past every hour.

---

# Companies currently monitored

- Audi F1 / Sauber Group / Sauber Technologies
- Audi Formula Racing student opportunities (finance/experience filter still applies)
- Ford Racing only
- McLaren Racing
- Aston Martin F1 Team
- Williams Racing
- Cadillac Formula 1 Team
- Mercedes-AMG PETRONAS F1 Team
- Red Bull Racing & Technology
- Andretti Global
- Visa Cash App Racing Bulls
- Alpine Racing
- Haas F1 Team
- Ferrari

Ford Global Finance and Ford Credit Services are not in `config.json`.

---

# What qualifies as a match

The configuration covers direct finance/accounting roles and close experience matches, including:

- Finance, FP&A, accounting, controller, treasury, tax, audit
- Cost cap, cost analysis, financial control, budgeting, forecasting
- Commercial finance, pricing, revenue, risk, credit
- Consolidation, reporting, financial systems, business planning
- Program finance, business analysis, planning analysis, strategy
- Program-management analysis, procurement/sourcing analysis
- Licensing, sponsorship, partnerships, and commercial strategy

It excludes common false matches such as production controller, material controller, controls engineer, document controller, race control, and vehicle-control engineering roles.

Edit `config.json` to add or remove title phrases later.

---

# Reading an ntfy job alert

A real alert will contain:

- Job title
- Employer
- Location, when supplied by the employer
- Source posting timestamp, when available
- Direct job link

Tapping the notification should open the job link.

---

# Troubleshooting

## No test notification

Check that the repository secret is named exactly:

```text
NTFY_TOPIC
```

and that its value exactly matches the topic subscribed to in the ntfy app.

Then manually run the workflow again with the test box checked.

## Workflow cannot push the database

Open:

```text
Settings → Actions → General → Workflow permissions
```

Select **Read and write permissions** and save.

## First run sends no jobs

That is intentional. The first run establishes the current baseline. Only jobs first detected after initialization are sent.

## A source reports zero jobs

Open the workflow run and expand **Check career sites once**. A zero may mean the employer currently has no public vacancies, or its careers page/API changed. The rest of the sources continue running independently.

## Workflow becomes disabled

Public scheduled workflows can be disabled after 60 days without repository activity. The included workflow updates `.state/heartbeat.txt` approximately monthly to generate activity. If GitHub still disables it, open **Actions → Motorsport Job Watcher** and click **Enable workflow**.

## Pause all notifications

Open **Actions → Motorsport Job Watcher**, click the three-dot menu, then select **Disable workflow**.

## Start it again

Open the disabled workflow and click **Enable workflow**, then run it manually once.

---

# Official references

- GitHub scheduled workflows: `https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule`
- GitHub Actions billing: `https://docs.github.com/en/billing/concepts/product-billing/github-actions`
- GitHub repository secrets: `https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets`
- ntfy publishing: `https://docs.ntfy.sh/publish/`
