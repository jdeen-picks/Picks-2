#!/usr/bin/env python3
"""football-data.org runner (free tier). Usage: python fd_run.py [--mock] [--days N]
Key: environment variable FOOTBALL_DATA_KEY (not needed with --mock). Standard library only.
What it does: 1 call for the upcoming fixtures, 1 call per competition for the season's finished matches
(form, season averages), 1 call per fixture for head-to-head. ~25 calls, ~3 minutes under the 10/min limit.
Writes docs/data/fd_picks.json. Injuries and bookmaker prices are NOT on the free tier: put them in
data/manual.json (see README_fd.md) and the runner will use them."""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error
import model as M, extras2 as X

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "data")

class Api:
    def __init__(self, key, base, mock=None):
        self.key, self.base, self.mock, self.calls = key, base, mock, 0
    def get(self, path, **params):
        if self.mock is not None: return self.mock(path, params)
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"X-Auth-Token": self.key})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r: data = json.load(r)
                self.calls += 1; time.sleep(6.5)            # free tier: 10 calls per minute
                return data
            except urllib.error.HTTPError as e:
                if e.code == 429: print("rate limited, waiting 60s"); time.sleep(60); continue
                if e.code in (400, 403, 404): print("not available on this plan:", path, e.code); return None
                print("HTTP", e.code, path); time.sleep(8)
            except Exception as e:
                print("request failed", path, e); time.sleep(8)
        return None

def goals(m):
    s = (m.get("score") or {}).get("fullTime") or {}
    return s.get("home"), s.get("away")

def team_stats(finished, tid, n):
    """finished: all finished matches (any competition), newest first. Returns form (last n) and season stats."""
    mine = []
    for m in finished:
        hg, ag = goals(m)
        if hg is None or ag is None: continue
        if m["homeTeam"]["id"] == tid: mine.append((hg, ag))
        elif m["awayTeam"]["id"] == tid: mine.append((ag, hg))
    def avg(lst): return (len(lst), sum(x[0] for x in lst) / len(lst), sum(x[1] for x in lst) / len(lst)) if lst else (0, None, None)
    return avg(mine[:n]), avg(mine)

def h2h_stats(matches, home_id):
    n = tot = w = l = 0
    for m in matches or []:
        hg, ag = goals(m)
        if hg is None or ag is None: continue
        if m["homeTeam"]["id"] != home_id: hg, ag = ag, hg
        n += 1; tot += hg + ag; w += hg > ag; l += hg < ag
    return dict(h2h_n=n, h2h_tot=(tot / n if n else None), h2h_w=w, h2h_l=l)

CORE = [("FT 1X2", None), ("FT DC", None), ("FT OU 1.5", None), ("FT OU 2.5", None), ("FT OU 3.5", None), ("FT OU 4.5", None),
        ("FT BTTS", None), ("FT AH -0.5", None), ("FT AH 0.5", None), ("FT AH -1.5", None), ("FT AH 1.5", None),
        ("FT TTH 0.5", None), ("FT TTH 1.5", None), ("FT TTA 0.5", None), ("FT TTA 1.5", None),
        ("FT DC&T1.5", None), ("FT DC&T2.5", None), ("FT DC&T3.5", None), ("1H OU 0.5", None), ("1H OU 1.5", None)]

def label(key, o):
    """Plain-English name for a market line, as it appears on Sportybet."""
    t = key.split(" ", 1)[1] if " " in key else key; half = "1st half " if key.startswith("1H") else ""
    if t.startswith("OU "): return f"{half}{'Over' if o == 'O' else 'Under'} {t[3:]}"
    if t.startswith("AH "): return f"{half}Asian handicap {'Home' if o == 'H' else 'Away'} {('+' if (float(t[3:]) <= 0) == (o == 'A') and float(t[3:]) != 0 else '')}{(-float(t[3:]) if o == 'A' else float(t[3:])):g}"
    if t.startswith("TTH "): return f"Home team {'over' if o == 'O' else 'under'} {t[4:]}"
    if t.startswith("TTA "): return f"Away team {'over' if o == 'O' else 'under'} {t[4:]}"
    if t == "1X2": return {"H": "Home win", "D": "Draw", "A": "Away win"}[o]
    if t == "DC": return {"1X": "Home or Draw", "12": "Home or Away", "X2": "Draw or Away"}[o]
    if t == "BTTS": return "Both teams to score: " + ("Yes" if o == "Y" else "No")
    if t.startswith("DC&T"): return f"Double chance {o.split('&')[0]} & {'Over' if o.endswith('O') else 'Under'} {t[4:]}"
    return f"{key} {o}"

def shortlist(lam, S, min_chance):
    """No prices needed: markets the model rates >= min_chance, with the minimum Sportybet odds that would make each worth taking."""
    P = X.price_book(lam[0], lam[1], deep=False); out = []
    for key, _ in CORE:
        for o, (w, p, l) in P.get(key, {}).items():
            if p > 1e-9: continue
            if w >= min_chance:
                out.append(dict(name=label(key, o), market=key, outcome=o, chance=round(w, 3), fair_odds=round(1 / w, 2),
                                min_odds=round(max(S["minO"], (1 + S["minE"]) / w), 2)))
    return sorted(out, key=lambda r: -r["chance"])

def load_manual():
    p = os.path.join(HERE, "data", "manual.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def main():
    mock = "--mock" in sys.argv
    days = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--days"), 0)) or None
    cfg = json.load(open(os.path.join(HERE, "fd_config.json"))); days = days or cfg["days_ahead"]
    S = dict(M.DEFAULTS); n = cfg["form_games"]
    if mock:
        from selftest.mock_fd import mock_get
        api = Api("", cfg["base"], mock=mock_get)
    else:
        key = os.environ.get("FOOTBALL_DATA_KEY")
        if not key: sys.exit("Set FOOTBALL_DATA_KEY (free key from football-data.org).")
        api = Api(key, cfg["base"])
    today = datetime.date.today(); end = today + datetime.timedelta(days=days)
    codes = ",".join(cfg["competitions"])
    fx = api.get("/matches", dateFrom=today.isoformat(), dateTo=end.isoformat(), competitions=codes) or {}
    fixtures = [m for m in fx.get("matches", []) if m["status"] in ("SCHEDULED", "TIMED") and m["competition"]["code"] in cfg["competitions"]]
    fixtures = sorted(fixtures, key=lambda m: m["utcDate"])[:cfg["max_matches"]]
    need = sorted({m["competition"]["code"] for m in fixtures} | ({"CL"} if any(m["competition"]["code"] != "CL" for m in fixtures) and "CL" in cfg["competitions"] else set()))
    finished = []
    for c in need:                                   # one call per competition: season results
        d = api.get(f"/competitions/{c}/matches", status="FINISHED") or {}
        finished += d.get("matches", [])
    seen = set(); uniq = []
    for m in sorted(finished, key=lambda m: m["utcDate"], reverse=True):
        if m["id"] not in seen: seen.add(m["id"]); uniq.append(m)
    manual = load_manual(); results = []
    for f in fixtures:
        comp = cfg["competitions"][f["competition"]["code"]]; key = comp["key"]; eu = comp.get("european")
        h, a = f["homeTeam"], f["awayTeam"]
        (hn, hgf, hga), (hs, hgfs, hgas) = team_stats(uniq, h["id"], n)
        (an, agf, aga), (as_, agfs, agas) = team_stats(uniq, a["id"], n)
        hh = api.get(f"/matches/{f['id']}/head2head", limit=cfg["h2h_limit"]) or {}
        m = dict(comp=key, home=h["name"], away=a["name"], hlg=M.EU if eu else key, alg=M.EU if eu else key,
                 h_nf=hn, h_gff=hgf, h_gaf=hga, h_ns=hs, h_gfs=hgfs, h_gas=hgas,
                 a_nf=an, a_gff=agf, a_gaf=aga, a_ns=as_, a_gfs=agfs, a_gas=agas, **h2h_stats(hh.get("matches"), h["id"]))
        man = manual.get(f"{h['name']}|{a['name']}", {})
        m.update(man.get("inj", {}))
        lam = M.lambdas(m, S)
        e = dict(match=f"{h['name']} v {a['name']}", league=comp["name"], kickoff=f["utcDate"], form_games=[hn, an],
                 h2h_games=m["h2h_n"], injuries_entered=bool(man.get("inj")), data_ok=bool(lam),
                 xg=[round(x, 2) for x in lam] if lam else None, shortlist=[], picks=[])
        if lam:
            e["shortlist"] = shortlist(lam, S, cfg["list_min_chance"])
            if man.get("book"):
                r = X.scan(lam[0], lam[1], man["book"], S["minP"], S["minE"], S["minO"], S["gap"])
                e["picks"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in x.items()} for x in r if x["status"] == "PICK"][:8]
        results.append(e)
    os.makedirs(OUT, exist_ok=True)
    out = dict(generated=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
               source="football-data.org (free tier)", api_calls=api.calls, matches=results,
               note="Injuries and Sportybet prices are not on the free tier: add them in data/manual.json. 'min_odds' is the lowest price at which a shortlisted market is worth taking.")
    json.dump(out, open(os.path.join(OUT, "fd_picks.json"), "w"), indent=1)
    print(f"{today}: {len(fixtures)} fixtures, {sum(1 for r in results if r['data_ok'])} priced, calls={api.calls}")
    for r in results:
        print(f"\n{r['match']} ({r['league']}) xG {r['xg']}  form games {r['form_games']} h2h {r['h2h_games']}")
        for s in r["shortlist"][:6]: print(f"   {s['name']:<34} chance {s['chance']:.0%}  take only if odds >= {s['min_odds']}")
        for p in r["picks"][:4]: print(f"   PICK {p['market']} {p['outcome']} @{p['odds']} ({p['blended']:.0%})")

if __name__ == "__main__":
    main()
