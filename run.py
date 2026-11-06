#!/usr/bin/env python3
"""Daily picks runner. Usage: python run.py [--mock] [--date YYYY-MM-DD]
Reads API_FOOTBALL_KEY from the environment (not needed with --mock).
Writes docs/data/picks.json and docs/data/history.json. Standard library only."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
import model as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "data")

class Api:
    def __init__(self, key, base, mock=None):
        self.key, self.base, self.mock, self.calls, self.remaining = key, base, mock, 0, None
    def get(self, path, **params):
        if self.mock is not None: return self.mock(path, params)
        url = self.base + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"x-apisports-key": self.key})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self.remaining = r.headers.get("x-ratelimit-requests-remaining", self.remaining)
                    data = json.load(r)
                self.calls += 1
                time.sleep(6.5)  # free plan: 10 requests/minute
                if data.get("errors") and data["errors"] not in ([], {}):
                    print("API warning:", data["errors"], "for", path, params)
                return data.get("response", [])
            except Exception as e:
                print("request failed", path, params, e); time.sleep(8)
        return []

def team_form(fixtures, team_id, n):
    gf = ga = cnt = 0
    for f in fixtures:
        if f["fixture"]["status"]["short"] not in ("FT", "AET", "PEN"): continue
        sc = f["score"]["fulltime"]
        if sc["home"] is None or sc["away"] is None: continue
        home = f["teams"]["home"]["id"] == team_id
        gf += sc["home"] if home else sc["away"]; ga += sc["away"] if home else sc["home"]; cnt += 1
        if cnt >= n: break
    return (cnt, gf/cnt, ga/cnt) if cnt else (0, None, None)

def h2h_stats(fixtures, home_id):
    n = tot = w = l = 0
    for f in fixtures:
        sc = f["score"]["fulltime"]
        if sc["home"] is None or sc["away"] is None: continue
        h_is_home = f["teams"]["home"]["id"] == home_id
        hg, ag = (sc["home"], sc["away"]) if h_is_home else (sc["away"], sc["home"])
        n += 1; tot += hg+ag; w += hg > ag; l += hg < ag
    return dict(h2h_n=n, h2h_tot=(tot/n if n else None), h2h_w=w, h2h_l=l)

def parse_odds(resp):
    o = [None]*16
    if not resp: return o
    books = resp[0].get("bookmakers", [])
    if not books: return o
    for bet in books[0].get("bets", []):
        v = {x["value"]: float(x["odd"]) for x in bet.get("values", []) if x.get("odd")}
        name = bet.get("name")
        if name == "Match Winner": o[0], o[1], o[2] = v.get("Home"), v.get("Draw"), v.get("Away")
        elif name == "Double Chance": o[3], o[4], o[5] = v.get("Home/Draw"), v.get("Draw/Away"), v.get("Home/Away")
        elif name == "Draw No Bet": o[6], o[7] = v.get("Home"), v.get("Away")
        elif name == "Goals Over/Under":
            for i, key in ((8,"Over 1.5"),(9,"Under 1.5"),(10,"Over 2.5"),(11,"Under 2.5"),(12,"Over 3.5"),(13,"Under 3.5")): o[i] = v.get(key)
        elif name == "Both Teams Score": o[14], o[15] = v.get("Yes"), v.get("No")
    return o

def build_match(api, fx, cfg, lg):
    hid, aid = fx["teams"]["home"]["id"], fx["teams"]["away"]["id"]
    fid = fx["fixture"]["id"]; n = cfg.get("form_games", 8)
    season = fx["league"]["season"]
    hf = api.get("/fixtures", team=hid, season=season); af = api.get("/fixtures", team=aid, season=season)
    hf = sorted(hf, key=lambda f: f["fixture"]["timestamp"], reverse=True); af = sorted(af, key=lambda f: f["fixture"]["timestamp"], reverse=True)
    h_n, h_gf, h_ga = team_form(hf, hid, n); a_n, a_gf, a_ga = team_form(af, aid, n)
    h2h_all = api.get("/fixtures/headtohead", h2h=f"{hid}-{aid}")
    h2h_all = sorted(h2h_all, key=lambda f: f["fixture"]["timestamp"], reverse=True)[:5]
    h2h = h2h_stats(h2h_all, hid)
    inj = api.get("/injuries", fixture=fid)
    hi = sum(1 for i in inj if i["team"]["id"] == hid); ai = sum(1 for i in inj if i["team"]["id"] == aid)
    odds = parse_odds(api.get("/odds", fixture=fid, bookmaker=cfg.get("bookmaker_id", 8)))
    key = lg["key"]; eu = lg.get("european")
    m = dict(date=fx["fixture"]["date"][:10], comp=key, home=fx["teams"]["home"]["name"], away=fx["teams"]["away"]["name"],
             hlg=M.EU if eu else key, alg=M.EU if eu else key,
             h_nf=h_n, h_gff=h_gf, h_gaf=h_ga, a_nf=a_n, a_gff=a_gf, a_gaf=a_ga,
             # position of injured players is unknown from this API: count each as a half-weight midfielder (capped at 4)
             hi_mid=min(hi, 4), ai_mid=min(ai, 4), **h2h)
    return m, odds

def load_history():
    p = os.path.join(OUT, "history.json")
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return []

def settle_history(api, hist):
    ids = [h["fixture_id"] for h in hist if h["result"] == "Pending"][:20]
    if not ids: return
    res = api.get("/fixtures", ids="-".join(str(i) for i in ids))
    by = {f["fixture"]["id"]: f for f in res}
    for h in hist:
        f = by.get(h["fixture_id"])
        if h["result"] != "Pending" or not f: continue
        st = f["fixture"]["status"]["short"]
        sc = f["score"]["fulltime"]
        if st in ("FT", "AET", "PEN") and sc["home"] is not None:
            h["result"] = M.settle(h["market"], sc["home"], sc["away"]); h["score"] = f'{sc["home"]}-{sc["away"]}'
        elif st in ("PST", "CANC", "ABD", "AWD", "WO"): h["result"] = "Void"

def record(hist):
    w = sum(h["result"] == "Win" for h in hist); l = sum(h["result"] == "Loss" for h in hist)
    p = sum(h["result"] == "Pending" for h in hist); prof = 0.0
    for h in hist:
        if h["result"] == "Win": prof += h["stake"]*(h["odds"]-1)
        elif h["result"] == "Loss": prof -= h["stake"]
    return dict(wins=w, losses=l, pending=p, profit=round(prof, 2), settled=w+l)

def main():
    mock = "--mock" in sys.argv
    date = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--date"), datetime.date.today().isoformat())
    cfg = json.load(open(os.path.join(HERE, "config.json")))
    S = dict(M.DEFAULTS); S.update(cfg.get("settings", {}))
    if mock:
        from selftest.mock_api import mock_get
        api = Api("", cfg["api_base"], mock=mock_get)
    else:
        key = os.environ.get("API_FOOTBALL_KEY")
        if not key: sys.exit("Set API_FOOTBALL_KEY (see README step 3).")
        api = Api(key, cfg["api_base"])
    os.makedirs(OUT, exist_ok=True)
    hist = load_history()
    settle_history(api, hist)
    fixtures = [f for f in api.get("/fixtures", date=date) if str(f["league"]["id"]) in cfg["leagues"]
                and f["fixture"]["status"]["short"] in ("NS", "TBD")][:cfg.get("max_matches_per_day", 14)]
    results, picks = [], []
    for fx in fixtures:
        lg = cfg["leagues"][str(fx["league"]["id"])]
        try:
            m, odds = build_match(api, fx, cfg, lg)
            e = M.evaluate(m, odds, S)
        except Exception as ex:
            print("skipped", fx["teams"], ex); continue
        entry = dict(fixture_id=fx["fixture"]["id"], match=f'{m["home"]} v {m["away"]}', league=lg["name"], kickoff=fx["fixture"]["date"],
                     status=e["status"], xg=[round(x, 2) for x in e["lam"]] if e.get("lam") else None, pick=None,
                     markets=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in e["markets"]])
        if e["pick"]:
            p = e["pick"]; entry["pick"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}
            picks.append(dict(p, match=entry["match"], fixture_id=entry["fixture_id"]))
        results.append(entry)
    slip = M.best_slip(picks, S)
    known = {(h["fixture_id"], h["market"]) for h in hist}
    for p in picks:
        if (p["fixture_id"], p["name"]) not in known:
            hist.append(dict(date=date, fixture_id=p["fixture_id"], match=p["match"], market=p["name"], odds=p["odds"],
                             blended=round(p["blended"], 4), stake=S["stake"], result="Pending", score=None))
    out = dict(generated=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")+"Z", date=date, matches=results,
               slip=slip and dict(odds=round(slip["odds"], 2), p=round(slip["p"], 4), legs=[dict(match=slip[x]["match"], market=slip[x]["name"], odds=slip[x]["odds"]) for x in ("a", "b")]),
               record=record(hist), api_calls=api.calls, requests_remaining=api.remaining)
    json.dump(out, open(os.path.join(OUT, "picks.json"), "w"), indent=1)
    json.dump(hist, open(os.path.join(OUT, "history.json"), "w"), indent=1)
    print(f"{date}: {len(fixtures)} matches, {len(picks)} picks, slip={'yes' if slip else 'no'}, calls={api.calls}")

if __name__ == "__main__":
    main()
