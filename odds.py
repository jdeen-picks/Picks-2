"""Reference bookmaker odds from The Odds API (the-odds-api.com, free key in ODDS_API_KEY). Standard library only.
These are the MEDIAN prices across many European bookmakers, NOT Sportybet prices. They are only a guide: always confirm on Sportybet.
Covers: win/draw/win, double chance (worked out from win/draw/win), over/under (main line), Asian handicap (main line).
Not covered: both teams to score, team goals, combined markets. Cost: 3 credits per league per run (h2h, totals, spreads)."""
import json, statistics, urllib.request, urllib.parse
from news import same_team

BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"

def fetch_league(sport, key, regions="eu", markets="h2h,totals,spreads", getter=None):
    url = BASE.format(sport=sport) + "?" + urllib.parse.urlencode(dict(apiKey=key, regions=regions, markets=markets, oddsFormat="decimal"))
    try:
        if getter: return getter(url)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "picks-bot"}), timeout=30) as r:
            left = r.headers.get("x-requests-remaining"); print("Odds API credits left:", left)
            return json.load(r)
    except Exception as e:
        print("Odds API unavailable:", e); return None

def _med(xs): return round(statistics.median(xs), 2) if xs else None

def event_book(ev):
    """One event -> {market key: {outcome: (median price, bookmakers)}} in the model's own market names."""
    h, a = ev["home_team"], ev["away_team"]; col = {}
    def add(mk, o, price): col.setdefault((mk, o), []).append(price)
    for b in ev.get("bookmakers", []):
        for m in b.get("markets", []):
            outs = m.get("outcomes", [])
            if m["key"] == "h2h":
                for o in outs:
                    add("FT 1X2", "D" if o["name"] == "Draw" else ("H" if o["name"] == h else "A"), o["price"])
            elif m["key"] == "totals":
                for o in outs: add(f"FT OU {o['point']:g}", "O" if o["name"] == "Over" else "U", o["price"])
            elif m["key"] == "spreads":
                for o in outs:
                    if o["name"] == h: add(f"FT AH {o['point']:g}", "H", o["price"])
                    elif o["name"] == a: add(f"FT AH {-o['point']:g}", "A", o["price"])
    book = {}
    for (mk, o), xs in col.items():
        if len(xs) >= 2 or True: book.setdefault(mk, {})[o] = (_med(xs), len(xs))
    x = book.get("FT 1X2", {})
    if all(k in x for k in "HDA"):                         # double chance, worked out from the three win/draw/win prices
        ph, pd, pa = (1 / x[k][0] for k in "HDA")
        book["FT DC"] = {"1X": (round(1 / (ph + pd), 2), x["H"][1]), "12": (round(1 / (ph + pa), 2), x["H"][1]), "X2": (round(1 / (pd + pa), 2), x["H"][1])}
    return book

def find_event(events, home, away):
    for ev in events or []:
        if same_team(ev["home_team"], home) and same_team(ev["away_team"], away): return ev
    return None

def plain(book): return {mk: {o: v[0] for o, v in outs.items()} for mk, outs in book.items()}
