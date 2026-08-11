# V5 Missed-Role Fix

Replace these files in the GitHub repository root:

1. `job_watcher.py`
2. `config.json`
3. `test_job_watcher.py` (recommended, but not required for scheduled execution)

The GitHub workflow file does **not** need to change for V5.

## What V5 changes

### Better matching

Adds title support for:
- Business Performance Analyst / Business Performance
- Accounts Assistant / Finance Assistant / Accounts Clerk / Finance Administrator
- Financial Regulations
- Internal Controls Analyst

Existing buyer/procurement/purchasing/sourcing terms remain enabled.

### Finance department fallback

A title that is vague can now match when high-confidence ATS metadata explicitly identifies the role as Finance or Financial Accounting. This uses the new `title_fallback_any` filter rather than making every description containing the word "finance" a match.

### Detail-page enrichment for link-based sources

Mercedes, Williams, and VCARB now open the official job detail page and recover the title/visible detail text before filtering. This avoids misses caused by listing-card anchors such as "View Details" or incomplete card text.

### Red Bull Racing

The Red Bull Racing link pattern now accepts both:
- `/job/...`
- `/jobs/preview/<id>`

This covers the URL form used by the Business Performance Analyst posting.

### Ford Racing

The source still prefers Ford Racing / Ford Performance / motorsport metadata. It now also allows a tightly scoped Internal Control Analyst title exception so the requested Internal Control Analyst posting is not rejected simply because Ford's Oracle API omitted Racing language from its metadata.

### Stellantis - Auburn Hills

Still requires Auburn Hills. Adds:
- Sales Analyst / Sales Planning / Sales Operations / Sales Strategy
- Marketing Analyst / Marketing Operations / Marketing Strategy
- Market Analyst / Market Intelligence / Business Intelligence
- Incentive(s) Analyst
- Dealer Performance / Dealer Network / Network Development
- Product Planning / Product Planner
- Commercial Planning / Sales Forecasting
- Brand Analyst / Brand Strategy

Licensing, merchandising, finance, accounting, commercial, strategy, and existing role families remain enabled.

Stellantis detail pages now prefer the actual page title/job heading and retain the visible detail text for matching.

## Regression tests included

The local test suite now explicitly checks that these role families match:
- Red Bull Racing — Business Performance Analyst
- Mercedes F1 — Finance Business Partner
- Williams F1 — Accounts Payable Specialist
- Aston Martin F1 — Accounts Assistant
- VCARB — Buyer (Composite)
- Ford — Internal Control Analyst
- Stellantis — Commercial Financial Analyst

It also tests Auburn Hills-only Stellantis sales/marketing expansion and Finance-department metadata fallback.

## After uploading

Run:

`Actions -> Motorsport Job Watcher -> Run workflow`

Because this is a manual run, you should receive the full current-match ntfy summary. Inspect the Actions log for `REJECTED [...]` lines if any of the known roles are still missing.
