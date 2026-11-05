# Daily Match Picks (automatic)

Every morning a free GitHub robot fetches the day's matches, runs the same model as your spreadsheet and phone app,
and updates a web page on your phone. It also settles yesterday's picks and keeps a public track record.

READ THIS FIRST
- Nothing here is guaranteed or risk free. The model is untested. Do not sell picks until the track record has 100+ settled picks, and check Ghana's Gaming Commission rules (or ask a lawyer) before charging anyone.
- This code was tested only against FAKE data shaped like API-Football's documented format. It has never talked to the real API. The first real run may need a small fix (see "If something fails").
- Free API plans sometimes block the current season. Step 2 tells you how to test that in 2 minutes.

## Setup (about 20 minutes, all free, all on your phone or any computer)

1. Create a GitHub account at github.com. Make a new repository named `picks`, set it to Public (GitHub Pages is free for public repos), and upload every file in this folder, keeping the folders (`.github/workflows/daily.yml`, `docs/`, `selftest/`). Easiest: on a computer, drag the unzipped files into the repository page.
2. Create an API-Football account at dashboard.api-football.com (free plan, 100 requests per day). Copy your API key. Test it: in the dashboard's "Fixtures" tool request today's date, and also pick one team and "last 5". If it says your plan cannot access the current season, the free plan will not work for live use and you must either upgrade (paid) or keep using the spreadsheet/phone app.
3. In your repository: Settings > Secrets and variables > Actions > New repository secret. Name `API_FOOTBALL_KEY`, value = your key.
4. Settings > Pages > Build from branch > `main` and folder `/docs`. Your page appears at `https://YOURNAME.github.io/picks/`.
5. Actions tab > "daily-picks" > Run workflow. Wait about 10 minutes (the free plan allows 10 calls per minute, so it runs slowly on purpose). Open your page.

After that it runs by itself every day at 08:00 Ghana time.

## What it uses per day
About 5 API calls per match plus 2. With the default limit of 14 matches that is about 72 calls, under the free 100. Change `max_matches_per_day` and the league list in `config.json`.

## If something fails
- Open the Actions tab, click the red run, read the log. "API warning" lines show what the API refused.
- Bookmaker id 8 is assumed to be Bet365 and the odds names ("Match Winner", "Goals Over/Under", "Both Teams Score", "Double Chance", "Draw No Bet") are assumed from the documentation. If odds come back empty, check the odds response in the dashboard and edit `parse_odds` in `run.py`.
- Injuries: the API does not say a player's position, so each injured player counts as a small midfielder-sized reduction (max 4). That is cruder than the spreadsheet.
- Teams in European games are all treated as "European games (no adjustment)" for league strength.
- Test offline any time: `python run.py --mock --date 2026-11-05` (no key needed).

## Being honest with customers later
Show the full track record (this page does), never use "guaranteed" or "sure", show 18+ and responsible-gambling notices, and never hide losing days.
