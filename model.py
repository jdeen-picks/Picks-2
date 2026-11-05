"""Match Model core - Python port of core.js / Betting_Model.xlsx (same maths)."""
import math

MARKETS = ["Home win","Draw","Away win","Home or Draw","Draw or Away","Home or Away","Draw No Bet Home","Draw No Bet Away",
           "Over 1.5","Under 1.5","Over 2.5","Under 2.5","Over 3.5","Under 3.5","BTTS Yes","BTTS No"]
DEFAULTS = dict(wf=0.5,k=6,ref=1.35,ia=0.04,im=0.02,id=0.04,minA=0.75,maxD=1.35,h2w=0.10,h2t=0.06,trust=0.60,
                minE=0.03,minP=0.55,minO=1.15,gap=0.15,lo=1.90,hi=2.30,stake=15)
EU = "European games (no adjustment)"
LEAGUES = {EU:(1.45,1.20,1.00),"Europa League":(1.45,1.20,1.00),"Conference League":(1.45,1.20,1.00),"Champions League":(1.55,1.25,1.00),
 "England":(1.55,1.25,1.00),"Spain":(1.45,1.10,1.00),"Germany":(1.70,1.35,1.00),"Italy":(1.40,1.15,1.00),"France":(1.50,1.20,0.97),
 "Portugal":(1.45,1.10,0.90),"Netherlands":(1.70,1.35,0.90),"Belgium":(1.55,1.25,0.88),"Turkey":(1.55,1.25,0.88),"Scotland":(1.55,1.25,0.82),
 "Austria":(1.60,1.30,0.82),"Switzerland":(1.65,1.35,0.82),"Greece":(1.30,1.00,0.82),"Czechia":(1.60,1.25,0.82),"Poland":(1.55,1.25,0.80),
 "Norway":(1.75,1.40,0.80),"Denmark":(1.55,1.25,0.82),"Croatia":(1.50,1.20,0.78),"Israel":(1.45,1.15,0.75),"Bulgaria":(1.45,1.15,0.72),
 "Cyprus":(1.50,1.20,0.72),"Qatar / Gulf":(1.60,1.25,0.78),"Ghana":(1.05,0.75,0.60),"Other league":(1.45,1.15,0.80)}

def _n(x):
    try:
        v = float(x); return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError): return 0.0
def _has(x):
    try: return x is not None and x != "" and math.isfinite(float(x))
    except (TypeError, ValueError): return False
def pois(k, l):
    p = math.exp(-l)
    for i in range(1, k+1): p *= l/i
    return p
def pcum(k, l): return sum(pois(i, l) for i in range(k+1))

def lambdas(m, S=DEFAULTS, L=LEAGUES):
    comp, hl, al = L.get(m.get("comp")), L.get(m.get("hlg")), L.get(m.get("alg"))
    if not (m.get("home") and m.get("away") and comp and hl and al and _n(m.get("h_nf"))>0 and _n(m.get("a_nf"))>0
            and all(_has(m.get(k)) for k in ("h_gff","h_gaf","a_gff","a_gaf"))): return None
    def side(p, sf):
        use_s = _n(m.get(p+"_ns"))>0 and _has(m.get(p+"_gfs")) and _has(m.get(p+"_gas"))
        gf = S["wf"]*_n(m[p+"_gff"])+(1-S["wf"])*_n(m[p+"_gfs"]) if use_s else _n(m[p+"_gff"])
        ga = S["wf"]*_n(m[p+"_gaf"])+(1-S["wf"])*_n(m[p+"_gas"]) if use_s else _n(m[p+"_gaf"])
        ne = S["wf"]*_n(m[p+"_nf"])+(1-S["wf"])*_n(m[p+"_ns"]) if use_s else _n(m[p+"_nf"])
        return (((ne*(gf*sf)+S["k"]*S["ref"])/(ne+S["k"]))/S["ref"], ((ne*(ga/sf)+S["k"]*S["ref"])/(ne+S["k"]))/S["ref"])
    h_att, h_def = side("h", hl[2]); a_att, a_def = side("a", al[2])
    def inj(ip):
        return (max(S["minA"], 1-(S["ia"]*_n(m.get(ip+"_att"))+S["im"]*_n(m.get(ip+"_mid")))),
                min(S["maxD"], 1+S["id"]*_n(m.get(ip+"_def"))+S["im"]*_n(m.get(ip+"_mid"))))
    hi_att, hi_def = inj("hi"); ai_att, ai_def = inj("ai")
    lh0 = comp[0]*h_att*a_def*hi_att*ai_def*(1+_n(m.get("h_mot")))
    la0 = comp[1]*a_att*h_def*ai_att*hi_def*(1+_n(m.get("a_mot")))
    tf = 1.0
    if _n(m.get("h2h_n"))>0 and _n(m.get("h2h_tot"))>0:
        tf = max(0.9, min(1.1, 1+S["h2w"]*(min(_n(m["h2h_n"]),5)/5)*(_n(m["h2h_tot"])/(lh0+la0)-1)))
    tilt = 0.0 if _n(m.get("h2h_n"))<=0 else max(-0.08, min(0.08, S["h2t"]*(_n(m.get("h2h_w"))-_n(m.get("h2h_l")))/_n(m["h2h_n"])))
    cl = lambda x: max(0.15, min(4.5, x))
    return cl(lh0*tf*(1+tilt)), cl(la0*tf*(1-tilt))

def probs(lh, la):
    ph = sum(pois(i, lh)*pcum(i-1, la) for i in range(1, 11))
    pd = sum(pois(i, lh)*pois(i, la) for i in range(11))
    pa = 1-ph-pd; t = lh+la
    o15, o25, o35 = 1-pcum(1,t), 1-pcum(2,t), 1-pcum(3,t)
    bt = (1-math.exp(-lh))*(1-math.exp(-la))
    return [ph,pd,pa,ph+pd,pd+pa,ph+pa,ph/(ph+pa),pa/(ph+pa),o15,1-o15,o25,1-o25,o35,1-o35,bt,1-bt]

def market_probs(o):
    r = [None]*16
    if all(_has(o[i]) for i in (0,1,2)):
        s = sum(1/o[i] for i in (0,1,2)); r[0],r[1],r[2] = [(1/o[i])/s for i in (0,1,2)]
        r[3]=r[0]+r[1]; r[4]=r[1]+r[2]; r[5]=r[0]+r[2]; r[6]=r[0]/(r[0]+r[2]); r[7]=r[2]/(r[0]+r[2])
    for a, b in ((8,9),(10,11),(12,13),(14,15)):
        if _has(o[a]) and _has(o[b]):
            r[a] = (1/o[a])/(1/o[a]+1/o[b]); r[b] = 1-r[a]
    return r

def evaluate(m, odds, S=DEFAULTS, L=LEAGUES):
    lam = lambdas(m, S, L)
    if not lam: return {"status":"Missing data","pick":None,"markets":[]}
    mod = probs(*lam); mk = market_probs(odds)
    check = mk[0] is not None and max(abs(mod[i]-mk[i]) for i in (0,1,2)) > S["gap"]
    rows, best = [], None
    for k in range(16):
        if not _has(odds[k]): continue
        o = float(odds[k]); bl = mod[k] if mk[k] is None else S["trust"]*mod[k]+(1-S["trust"])*mk[k]; edge = bl*o-1
        ok = (not check and o>=S["minO"] and bl>=S["minP"] and edge>=S["minE"] and (mk[k] is None or abs(mod[k]-mk[k])<=S["gap"]))
        row = dict(name=MARKETS[k], odds=o, model=mod[k], market=mk[k], blended=bl, edge=edge, eligible=ok)
        rows.append(row)
        if ok and (best is None or edge>best["edge"]): best = row
    return {"status":"CHECK DATA" if check else "OK","lam":lam,"pick":best,"markets":rows,"total":sum(lam)}

def best_slip(picks, S=DEFAULTS):
    best = None
    for i in range(len(picks)):
        for j in range(i+1, len(picks)):
            o = picks[i]["odds"]*picks[j]["odds"]; p = picks[i]["blended"]*picks[j]["blended"]
            if S["lo"]<=o<=S["hi"] and (best is None or p>best["p"]): best = {"a":picks[i],"b":picks[j],"odds":o,"p":p}
    return best

def settle(market, hg, ag):
    """Return 'Win'/'Loss'/'Void' for a market name given the full-time score."""
    t = hg+ag
    res = {"Home win":hg>ag,"Draw":hg==ag,"Away win":ag>hg,"Home or Draw":hg>=ag,"Draw or Away":ag>=hg,"Home or Away":hg!=ag,
           "Over 1.5":t>1.5,"Under 1.5":t<1.5,"Over 2.5":t>2.5,"Under 2.5":t<2.5,"Over 3.5":t>3.5,"Under 3.5":t<3.5,
           "BTTS Yes":hg>0 and ag>0,"BTTS No":not(hg>0 and ag>0)}
    if market=="Draw No Bet Home": return "Void" if hg==ag else ("Win" if hg>ag else "Loss")
    if market=="Draw No Bet Away": return "Void" if hg==ag else ("Win" if ag>hg else "Loss")
    return "Win" if res[market] else "Loss"
