#!/usr/bin/env python3
"""Walk-forward test of the model. For every finished match, the model sees ONLY games played before it (same inputs as the live
page, except head-to-head and injuries, which cannot be rebuilt), builds its 65%+ shortlist, and each market is settled on the real score.
Question answered: when the model says X%, how often does it really happen?
Usage: python backtest.py [--mock]. Needs FOOTBALL_DATA_KEY. Writes docs/backtest.txt and prints the same report."""
import json, os, sys, collections, datetime
import model as M
from fd_run import Api, CORE, label, shortlist
HERE = os.path.dirname(os.path.abspath(__file__))

def settle(key, o, hg, ag, h1=None, a1=None):
    """Returns 1 win, 0 loss, None if it cannot be settled (missing half-time score)."""
    t = key.split(" ", 1)[1]; tot = hg + ag
    if t == "1X2": return int({"H": hg > ag, "D": hg == ag, "A": hg < ag}[o])
    if t == "DC": return int({"1X": hg >= ag, "12": hg != ag, "X2": ag >= hg}[o])
    if t == "BTTS": return int((hg > 0 and ag > 0) == (o == "Y"))
    if t.startswith("OU "):
        line = float(t[3:]); return int((tot > line) == (o == "O"))
    if t.startswith("AH "):
        line = float(t[3:]); return int((hg + line > ag) if o == "H" else (ag - line > hg))
    if t.startswith("TTH "): return int((hg > float(t[4:])) == (o == "O"))
    if t.startswith("TTA "): return int((ag > float(t[4:])) == (o == "O"))
    if t.startswith("DC&T"):
        dc, ou = o.split("&"); line = float(t[4:])
        return int({"1X": hg >= ag, "12": hg != ag, "X2": ag >= hg}[dc] and ((tot > line) == (ou == "O")))
    if key.startswith("1H OU"):
        if h1 is None or a1 is None: return None
        return int(((h1 + a1) > float(t[3:])) == (o == "O"))
    return None

def run_season(matches, cfg, S, n=8, min_games=5):
    """matches: finished matches of one season, any competition."""
    ms = sorted([m for m in matches if (m.get("score") or {}).get("fullTime", {}).get("home") is not None], key=lambda m: m["utcDate"])
    hist = collections.defaultdict(list)                      # team id -> [(goals for, goals against)] in time order
    rows = []
    def stat(tid):
        h = hist[tid]; last = h[-n:]
        f = lambda l: (len(l), (sum(x[0] for x in l) / len(l)) if l else None, (sum(x[1] for x in l) / len(l)) if l else None)
        return f(last), f(h)
    for m in ms:
        hid, aid = m["homeTeam"]["id"], m["awayTeam"]["id"]; code = m["competition"]["code"]
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        ht = (m["score"].get("halfTime") or {}); h1, a1 = ht.get("home"), ht.get("away")
        (hn, hgf, hga), (hs, hgfs, hgas) = stat(hid); (an, agf, aga), (as_, agfs, agas) = stat(aid)
        comp = cfg["competitions"].get(code)
        if comp and hn >= min_games and an >= min_games:
            mm = dict(comp=comp["key"], home=m["homeTeam"]["name"], away=m["awayTeam"]["name"], hlg=M.EU if comp.get("european") else comp["key"],
                      alg=M.EU if comp.get("european") else comp["key"], h_nf=hn, h_gff=hgf, h_gaf=hga, h_ns=hs, h_gfs=hgfs, h_gas=hgas,
                      a_nf=an, a_gff=agf, a_gaf=aga, a_ns=as_, a_gfs=agfs, a_gas=agas, h2h_n=0, h2h_tot=None, h2h_w=0, h2h_l=0)
            lam = M.lambdas(mm, S)
            if lam:
                for r in shortlist(lam, S, cfg["list_min_chance"]):
                    w = settle(r["market"], r["outcome"], hg, ag, h1, a1)
                    if w is not None: rows.append((r["chance"], w, r["market"], r["name"], m["utcDate"][:10], mm["home"] + " v " + mm["away"], r["min_odds"]))
        hist[hid].append((hg, ag)); hist[aid].append((ag, hg))
    return rows

def report(rows, n_matches):
    L = []; add = L.append
    add(f"BACKTEST: {n_matches} finished matches, {len(rows)} shortlist rows (model chance 65% or higher)")
    add("Each row = one market the model rated at 65%+ before kickoff, settled on the real score.")
    add("")
    add("chance band      rows   model says   actually won   gap")
    bins = [(.65, .70), (.70, .75), (.75, .80), (.80, .85), (.85, .90), (.90, 1.01)]
    for lo, hi in bins:
        b = [r for r in rows if lo <= r[0] < hi]
        if b:
            mp = sum(r[0] for r in b) / len(b); ap = sum(r[1] for r in b) / len(b)
            add(f"{int(lo*100)}-{min(int(hi*100),100)}%".ljust(15) + f"{len(b):5d}   {mp*100:7.1f}%     {ap*100:7.1f}%    {100*(ap-mp):+6.1f}")
    if rows:
        mp = sum(r[0] for r in rows) / len(rows); ap = sum(r[1] for r in rows) / len(rows)
        add("ALL".ljust(15) + f"{len(rows):5d}   {mp*100:7.1f}%     {ap*100:7.1f}%    {100*(ap-mp):+6.1f}")
    add(""); add("By market type (model says vs actually won):")
    fam = collections.defaultdict(list)
    for r in rows:
        k = r[2].split(" ", 1)[1]; k = "Over/Under " + k[3:] if k.startswith("OU") else ("Asian handicap" if k.startswith("AH") else ("Team goals" if k.startswith("TT") else ("Double chance + goals" if k.startswith("DC&") else ("Double chance" if k == "DC" else ("Both teams to score" if k == "BTTS" else k)))))
        if r[2].startswith("1H"): k = "1st half goals"
        fam[k].append(r)
    for k, b in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        if len(b) >= 15: add(f"  {k[:24].ljust(24)} rows {len(b):4d}   says {100*sum(r[0] for r in b)/len(b):5.1f}%   won {100*sum(r[1] for r in b)/len(b):5.1f}%")
    # simulated two-leg 'about 2.0' slips: legs from different matches on the same day with product of fair odds near 2.0 are not knowable without prices,
    # so instead report how often two independent 80%-type legs both win
    add(""); add("Worst-calibrated single rows to avoid (model 80%+ but actually under 70%):")
    for k, b in fam.items():
        hi = [r for r in b if r[0] >= .80]
        if len(hi) >= 15 and sum(r[1] for r in hi) / len(hi) < .70: add(f"  {k}: says {100*sum(r[0] for r in hi)/len(hi):.0f}% won {100*sum(r[1] for r in hi)/len(hi):.0f}% over {len(hi)} rows")
    return "\n".join(L)

def main():
    mock = "--mock" in sys.argv
    cfg = json.load(open(os.path.join(HERE, "fd_config.json"))); S = dict(M.DEFAULTS)
    if mock:
        from selftest.mock_backtest import mock_get
        api = Api("", cfg["base"], mock=mock_get)
    else:
        key = os.environ.get("FOOTBALL_DATA_KEY")
        if not key: sys.exit("Set FOOTBALL_DATA_KEY")
        api = Api(key, cfg["base"])
    today = datetime.date.today(); seasons = [today.year if today.month >= 7 else today.year - 1]; seasons.append(seasons[0] - 1)
    rows = []; total = 0
    for sea in seasons:
        pool = []
        for c in cfg["competitions"]:
            d = api.get(f"/competitions/{c}/matches", status="FINISHED", season=sea)
            if d: pool += d.get("matches", [])
        uniq = {m["id"]: m for m in pool}.values()
        print(f"season {sea}: {len(uniq)} finished matches downloaded")
        if uniq: total += len(uniq); rows += run_season(list(uniq), cfg, S)
    txt = report(rows, total); print(txt)
    if not mock:
        os.makedirs(os.path.join(HERE, "docs"), exist_ok=True); open(os.path.join(HERE, "docs", "backtest.txt"), "w").write(txt + "\n")
if __name__ == "__main__": main()
