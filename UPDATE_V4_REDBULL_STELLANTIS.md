# V4 update: Red Bull buyer roles + Stellantis parser fix

Replace these files in the GitHub repository root:

- `job_watcher.py`
- `config.json`

`requirements.txt` is unchanged from V3, but replacing it is harmless.

You do not need to replace the workflow file for this update.

## What changed

- Red Bull Racing is now rendered with headless Chrome instead of relying on the non-rendered HTML page.
- Red Bull and Stellantis job detail pages are opened and enriched from JobPosting JSON-LD/H1/location data.
- Added relevant purchasing/procurement titles: buyer, purchasing, procurement, sourcing, supply-chain analyst, purchasing analyst, procurement specialist, and sourcing specialist.
- Stellantis remains restricted to Auburn Hills, Michigan and still includes finance/accounting/business/strategy plus licensing/merchandising families.
- Red Bull and Stellantis now log rejected fetched jobs with a reason so parser/filter misses are visible in GitHub Actions.
- ntfy server fallback is hardened and the ntfy title uses an ASCII dash to avoid Unicode header errors.

## Test

After committing the two files:

1. Go to **Actions → Motorsport Job Watcher → Run workflow**.
2. Open **Check career sites once**.
3. Confirm Red Bull shows a non-zero fetched count if its careers page currently has openings.
4. Confirm `Commercial Financial Analyst` appears as a Stellantis match if it is still live in Auburn Hills.
5. Because this is a manual run, you should receive one current-jobs summary on ntfy.

If Stellantis or Red Bull rejects something unexpectedly, the log will now show lines such as:

`REJECTED [Stellantis - Auburn Hills] title='...' location='...' reason=...`
