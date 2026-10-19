# Vacancy bot

Checks 19 career sites every ~10 minutes on GitHub Actions and sends each new vacancy to Telegram once (title, company, experience, link).

## Files
- `sites.py`: list of sites. Add, remove or edit entries here.
- `scraper.py`: the scraper.
- `seen.json`: created automatically; IDs of vacancies already sent.
- `.github/workflows/scrape.yml`: runs every 10 minutes.
- `.github/workflows/doctor.yml`: manual test of every site; sends a report to Telegram and saves page HTML as a downloadable "debug-pages" file.

## Setup
1. Create the Telegram bot and get the chat ID (see instructions in chat).
2. Create a **public** GitHub repo and upload all files, keeping the `.github/workflows` folder structure.
3. Repo → Settings → Secrets and variables → Actions → New repository secret:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Actions tab → "Test all sites" → Run workflow. Check the Telegram report.
5. Actions tab → "Check vacancies" → Run workflow once. You get a "Now tracking" message; after that only new vacancies arrive.

## Options
- Receive current vacancies on the first run too: add `SEND_EXISTING: "true"` under `env:` of the "Scrape and notify" step in `scrape.yml` before the first run.
- Global jobs for Shell / Worley / Baker Hughes / SLB: delete the `country`/`location` line or `Kazakhstan` from the URL in `sites.py`.
