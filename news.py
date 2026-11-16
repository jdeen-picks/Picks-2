"""Injury and team-news lookup for fd_run.py. Standard library only. Every function fails soft: if a source is down
the match is simply marked 'team news not checked'.
Sources:
  1) Premier League: the official Fantasy Premier League feed (free, no key). Gives status (injured / doubtful /
     suspended), chance of playing and a news note for every player. Premier League matches only.
  2) Other leagues: API-Football (api-football.com) if you add a free key as the GitHub secret API_FOOTBALL_KEY.
     Optional. Its free plan may not cover the current season, in which case those matches stay 'not checked'.
Lineups are only published about an hour before kickoff, so the 07:00 run cannot include them."""
import json, re, urllib.request, urllib.parse, datetime

FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
APIF_URL = "https://v3.football.api-sports.io/injuries"
UA = {"User-Agent": "Mozilla/5.0 (compatible; picks-bot)"}
ALIAS = {"man city": "manchester city", "man utd": "manchester united", "spurs": "tottenham",
         "nott'm forest": "nottingham forest", "wolves": "wolverhampton", "newcastle": "newcastle united"}

def norm(s):
    s = (s or "").lower().replace("&", "and").replace(".", "")
    s = re.sub(r"\b(fc|afc|cf|ac|as|sc|sv|fk)\b", " ", s)
    s = re.sub(r"[^a-z' ]", " ", s)
    return ALIAS.get(re.sub(r"\s+", " ", s).strip(), re.sub(r"\s+", " ", s).strip())

def same_team(a, b):
    a, b = norm(a), norm(b)
    return bool(a and b and (a == b or a in b or b in a))

def _get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# ---------- Premier League (Fantasy feed) ----------
def fetch_fpl(getter=_get):
    try:
        return fpl_table(getter(FPL_URL))
    except Exception as e:
        print("FPL feed unavailable:", e); return None

def fpl_table(data):
    """-> {team name: [absence dicts]}. Players are 'key' if they play at least half the minutes of their team's top player."""
    teams = {t["id"]: t["name"] for t in data["teams"]}
    pos = {1: "def", 2: "def", 3: "mid", 4: "att"}          # keeper and defenders both weaken the defence
    by_team = {}
    for p in data["elements"]:
        by_team.setdefault(p["team"], []).append(p)
    table = {}
    for tid, players in by_team.items():
        top = max((p.get("minutes") or 0) for p in players) or 1
        out = []
        for p in players:
            st = p.get("status", "a")
            if st in ("a", "n"): continue                    # available, or not in the squad at all
            ch = p.get("chance_of_playing_next_round")
            if st == "d": w = 1 - (ch if ch is not None else 50) / 100
            else: w = 1.0                                     # injured / suspended / unavailable
            if w <= 0.2: continue
            key = (p.get("minutes") or 0) >= 0.5 * top
            out.append(dict(name=p.get("web_name"), pos=pos.get(p.get("element_type"), "mid"), status=st, w=round(w, 2),
                            key=key, note=(p.get("news") or "").strip()[:90]))
        table[teams[tid]] = out
    return table

# ---------- Other leagues (API-Football, optional key) ----------
def fetch_apif(key, league_id, date, season, getter=_get):
    try:
        d = getter(APIF_URL + "?" + urllib.parse.urlencode(dict(league=league_id, season=season, date=date)), {"x-apisports-key": key})
        if d.get("errors"): print("API-Football:", d["errors"]); return None
        table = {}
        for r in d.get("response", []):
            pl, tm = r["player"], r["team"]["name"]
            w = 0.5 if (pl.get("type") or "").lower().startswith("quest") else 1.0
            table.setdefault(tm, []).append(dict(name=pl.get("name"), pos=None, status="d" if w < 1 else "i", w=w, key=True,
                                                 note=(pl.get("reason") or "")[:90]))
        return table
    except Exception as e:
        print("API-Football unavailable:", e); return None

# ---------- Turn absences into model inputs ----------
def team_absences(table, team):
    if not table: return None
    for name, lst in table.items():
        if same_team(name, team): return lst
    return None

def inj_inputs(prefix, lst):
    """Absence list -> hi_att / hi_mid / hi_def style counts the model already understands. Only key players count."""
    c = dict(att=0.0, mid=0.0, de=0.0)
    for a in lst or []:
        if not a["key"]: continue
        if a["pos"] == "att": c["att"] += a["w"]
        elif a["pos"] == "def": c["de"] += a["w"]
        else: c["mid"] += a["w"] * (1 if a["pos"] == "mid" else 0.5)   # position unknown -> half a midfielder
    cap = lambda x: round(min(3.0, x), 2)
    return {f"{prefix}_att": cap(c["att"]), f"{prefix}_mid": cap(c["mid"]), f"{prefix}_def": cap(c["de"])}

def summary(lst):
    return [dict(name=a["name"], status={"i": "out", "s": "suspended", "u": "unavailable", "d": "doubtful"}.get(a["status"], a["status"]),
                 chance=None if a["status"] != "d" else round(1 - a["w"], 2), note=a["note"], key=a["key"]) for a in (lst or [])]
