# fd_run.py: daily shortlist from football-data.org (free)

1. Register free at football-data.org and copy your API token.
2. GitHub repo > Settings > Secrets and variables > Actions > New secret: name FOOTBALL_DATA_KEY, value = the token.
3. Copy these files into the repo: fd_run.py, fd_config.json, extras2.py, model.py, selftest/mock_fd.py, .github/workflows/fd-daily.yml, data/manual.json.
4. Actions tab > fd-daily-picks > Run workflow. Result: docs/data/fd_picks.json (also runs every day at 07:00 Ghana time).

Test offline first: `python fd_run.py --mock`

What you get per match: model goals, and a shortlist of markets rated 65%+ with the MINIMUM Sportybet odds worth taking.
You only open Sportybet for the few shortlisted markets and compare the price. If the price is at or above min_odds, it passes.

Not on the free tier: injuries, lineups, bookmaker prices. Add them in data/manual.json, key = "Home name|Away name" exactly as in fd_picks.json:
  "inj": counts of injured attackers/midfielders/defenders on each side (hi_* = home, ai_* = away)
  "book": Sportybet prices in the market keys used by extras2.py; the runner then lists real PICKs.
Form uses finished matches in the fetched competitions this season (league and Champions League), last 8 games blended with the season.
Competitions on the free tier: PL, PD, BL1, SA, FL1, PPL, DED, CL (plus Championship, Brasileirao, World Cup, Euros: edit fd_config.json).
