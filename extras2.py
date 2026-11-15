"""v4 market library: prices (almost) every market a bookmaker lists, from the same Poisson goal model.
Keys look like "FT OU 2.5", "1H AH -0.5", "FT HTFT". Every price is a (win, push, lose) triple so that
Asian / whole-number lines (stake returned on a push) are handled correctly.
Usage:  P = price_book(lh, la);  rows = scan(lh, la, book)   (book = {key: {outcome: decimal_odds}})
Path-dependent markets (lead by X, goals in a row, win from behind, 1UP/2UP, never down) use an exact
scorer-sequence DP: given N goals, each is the home side's with prob lh/(lh+la).
"""
import math
FH = 0.44          # share of goals expected in the 1st half
NMAX = 16

def pois(k, l):
    if l <= 0: return 1.0 if k == 0 else 0.0
    return math.exp(-l + k * math.log(l) - math.lgamma(k + 1))

def _dist(l, n=NMAX): return [pois(k, l) for k in range(n)]

def _joint(lh, la):
    a, b = _dist(lh), _dist(la)
    return [[a[i] * b[j] for j in range(NMAX)] for i in range(NMAX)]

def _tot(X):
    t = {}
    for i, r in enumerate(X):
        for j, p in enumerate(r): t[i + j] = t.get(i + j, 0) + p
    return t

def _diff(X):
    t = {}
    for i, r in enumerate(X):
        for j, p in enumerate(r): t[i - j] = t.get(i - j, 0) + p
    return t

def _bet(dist, line, sign):
    """Win/push/lose triple for a bet that wins when sign*(x-line)>0; quarter lines split in two."""
    def one(l):
        w = p = lo = 0.0
        for x, pr in dist.items():
            m = sign * (x - l)
            if m > 1e-9: w += pr
            elif m > -1e-9: p += pr
            else: lo += pr
        return w, p, lo
    if abs((line * 4) % 2 - 1) < 1e-9:                      # .25 / .75 lines
        a, b = one(line - 0.25), one(line + 0.25)
        return tuple((x + y) / 2 for x, y in zip(a, b))
    return one(line)

def _yes(p): return {"Y": (p, 0, 1 - p), "N": (1 - p, 0, p)}
def _wp(p): return (p, 0.0, 1 - p)

def _res(d): return "H" if d > 0 else ("D" if d == 0 else "A")

def _seq(lh, la, nmax=11):
    """Exact path stats from the scorer-sequence DP."""
    if lh + la <= 0: return None
    p = lh / (lh + la)
    layer = {(0, 0, 0, 0, 0, 0, 0): 1.0}
    layers = [layer]
    for _ in range(nmax):
        new = {}
        for (d, mh, ma, last, run, rh, ra), pr in layer.items():
            nd = d + 1; r = min(run + 1, 3) if last == 1 else 1
            k = (nd, min(max(mh, nd), 3), ma, 1, r, max(rh, r), ra); new[k] = new.get(k, 0) + pr * p
            nd = d - 1; r = min(run + 1, 3) if last == 2 else 1
            k = (nd, mh, min(max(ma, -nd), 3), 2, r, rh, max(ra, r)); new[k] = new.get(k, 0) + pr * (1 - p)
        layer = new; layers.append(layer)
    w = [pois(n, lh + la) for n in range(nmax + 1)]; sw = sum(w)
    S = {}
    def add(name, cond):
        S[name] = sum(w[n] / sw * sum(pr for s, pr in layers[n].items() if cond(*s)) for n in range(nmax + 1))
    for x in (1, 2, 3):
        add(f"leadH{x}", lambda d, mh, ma, l, r, rh, ra, x=x: mh >= x)
        add(f"leadA{x}", lambda d, mh, ma, l, r, rh, ra, x=x: ma >= x)
        add(f"leadAny{x}", lambda d, mh, ma, l, r, rh, ra, x=x: max(mh, ma) >= x)
    for x in (2, 3):
        add(f"rowAny{x}", lambda d, mh, ma, l, r, rh, ra, x=x: max(rh, ra) >= x)
        add(f"rowH{x}", lambda d, mh, ma, l, r, rh, ra, x=x: rh >= x)
        add(f"rowA{x}", lambda d, mh, ma, l, r, rh, ra, x=x: ra >= x)
    add("fromBehindH", lambda d, mh, ma, l, r, rh, ra: d > 0 and ma >= 1)
    add("fromBehindA", lambda d, mh, ma, l, r, rh, ra: d < 0 and mh >= 1)
    add("neverDownH", lambda d, mh, ma, l, r, rh, ra: d > 0 and ma == 0)
    add("neverDownA", lambda d, mh, ma, l, r, rh, ra: d < 0 and mh == 0)
    add("draw", lambda d, mh, ma, l, r, rh, ra: d == 0)
    add("1upH_or_draw", lambda d, mh, ma, l, r, rh, ra: mh >= 1 or d == 0)
    add("1upA_or_draw", lambda d, mh, ma, l, r, rh, ra: ma >= 1 or d == 0)
    add("2upH_or_win", lambda d, mh, ma, l, r, rh, ra: mh >= 2 or d > 0)     # 1X2-2UP: paid early at +2, else normal result
    add("2upA_or_win", lambda d, mh, ma, l, r, rh, ra: ma >= 2 or d < 0)
    return S

def _half_block(sc, lh, la, out, deep=True):
    """Markets that exist for both full time (sc='FT') and 1st half (sc='1H')."""
    X = _joint(lh, la); T = _tot(X); D = _diff(X)
    ph = sum(p for d, p in D.items() if d > 0); pd = D.get(0, 0); pa = 1 - ph - pd
    out[f"{sc} 1X2"] = {"H": _wp(ph), "D": _wp(pd), "A": _wp(pa)}
    out[f"{sc} DC"] = {"1X": _wp(ph + pd), "12": _wp(ph + pa), "X2": _wp(pd + pa)}
    out[f"{sc} DNB"] = {"H": (ph, pd, pa), "A": (pa, pd, ph)}
    for L in (0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6):
        out[f"{sc} OU {L}"] = {"O": _bet(T, L, 1), "U": _bet(T, L, -1)}
    for L in (2.25, 2.75, 3.25, 3.75):
        out[f"{sc} OU {L}"] = {"O": _bet(T, L, 1), "U": _bet(T, L, -1)}
    for h in (-3.5, -3, -2.5, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, -0.25, 0.25, -0.75, 0.75, -1.25, 1.25, -1.75, 1.75):
        out[f"{sc} AH {h:g}"] = {"H": _bet(D, -h, 1), "A": _bet(D, -h, -1)}
    for a, b in ((0, 1), (1, 0), (0, 2), (2, 0), (0, 3), (3, 0), (0, 4), (4, 0), (0, 5), (5, 0)):
        j = d = g = 0.0
        for x, pr in D.items():
            s = x + a - b
            if s > 0: j += pr
            elif s == 0: d += pr
            else: g += pr
        out[f"{sc} HC {a}:{b}"] = {"H": _wp(j), "D": _wp(d), "A": _wp(g)}
    A, B = _dist(lh), _dist(la)
    for side, dd in (("H", {i: A[i] for i in range(NMAX)}), ("A", {j: B[j] for j in range(NMAX)})):
        for L in (0.5, 1.5, 2.5, 3.5):
            out[f"{sc} TT{side} {L}"] = {"O": _bet(dd, L, 1), "U": _bet(dd, L, -1)}
        out[f"{sc} OE{side}"] = {"Odd": _wp(sum(p for k, p in dd.items() if k % 2)), "Even": _wp(sum(p for k, p in dd.items() if k % 2 == 0))}
        for k in range(0, 4):
            pk = dd[k] if k < 3 else 1 - dd[0] - dd[1] - dd[2]
            out[f"{sc} EXCL{side} {k}"] = {"Y": _wp(1 - pk)}
            out[f"{sc} EXT{side} {k}{'+' if k == 3 else ''}"] = {"Y": _wp(pk)}          # excluded number of goals: wins if team goals != k
        for lo, hi in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3), (1, 99), (2, 99), (3, 99), (4, 99)):
            out[f"{sc} GB{side} {lo}-{hi}"] = {"Y": _wp(sum(p for k, p in dd.items() if lo <= k <= hi))}
        out[f"{sc} CS{side}"] = {"Y": _wp(A[0] if side == "A" else B[0])}   # opponent scores 0 => clean sheet
    ptot0 = T[0]
    out[f"{sc} BTTS"] = {"Y": _wp((1 - A[0]) * (1 - B[0])), "N": _wp(1 - (1 - A[0]) * (1 - B[0]))}
    out[f"{sc} OE"] = {"Odd": _wp(sum(p for k, p in T.items() if k % 2)), "Even": _wp(sum(p for k, p in T.items() if k % 2 == 0))}
    for k in range(0, 4):
        pk = T.get(k, 0) if k < 3 else 1 - T[0] - T[1] - T[2]
        out[f"{sc} EX {k}{'+' if k == 3 else ''}"] = {"Y": _wp(pk)}
    for lo in range(0, 8):
        for hi in list(range(lo, 8)) + [99]:
            if lo == 0 and hi == 99: continue
            out[f"{sc} GB {lo}-{hi}"] = {"Y": _wp(sum(p for k, p in T.items() if lo <= k <= hi))}
    for k in range(0, 8):
        out[f"{sc} EXACT {k}"] = {"Y": _wp(T.get(k, 0))}
    out[f"{sc} EXACT 6+"] = {"Y": _wp(1 - sum(T.get(k, 0) for k in range(6)))}
    out[f"{sc} CS"] = {f"{i}:{j}": _wp(X[i][j]) for i in range(6) for j in range(6)}
    p1h = lh / (lh + la) * (1 - ptot0) if lh + la > 0 else 0
    out[f"{sc} FIRSTGOAL"] = {"H": _wp(p1h), "None": _wp(ptot0), "A": _wp((1 - ptot0) - p1h)}
    for r, pr in (("H", ph), ("D", pd), ("A", pa)):                    # 1X2 & goals
        for L in (1.5, 2.5, 3.5):
            out.setdefault(f"{sc} 1X2&T{L}", {})
    for L in (1.5, 2.5, 3.5, 4.5):
        r = {}
        for res in "HDA":
            for ou in "UO":
                r[f"{res}&{ou}"] = 0.0
        for i in range(NMAX):
            for j in range(NMAX):
                r[f"{_res(i - j)}&{'O' if i + j > L else 'U'}"] += X[i][j]
        out[f"{sc} 1X2&T{L}"] = {k: _wp(v) for k, v in r.items()}
    for res in "HDA":
        out[f"{sc} 1X2&BTTS"] = out.get(f"{sc} 1X2&BTTS", {})
    r = {}
    for res in "HDA":
        for g in ("Y", "N"): r[f"{res}&{g}"] = 0.0
    for i in range(NMAX):
        for j in range(NMAX):
            r[f"{_res(i - j)}&{'Y' if i > 0 and j > 0 else 'N'}"] += X[i][j]
    out[f"{sc} 1X2&BTTS"] = {k: _wp(v) for k, v in r.items()}

    # --- result-combination and misc markets -------------------------------------------------
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        r = {f"{dc}&{ou}": 0.0 for dc in ("1X", "12", "X2") for ou in "UO"}
        u = {f"{res}&{ou}": 0.0 for res in "HDA" for ou in "UO"}
        for i in range(NMAX):
            for j in range(NMAX):
                res = _res(i - j); ou = "O" if i + j > L else "U"; u[f"{res}&{ou}"] += X[i][j]
        for ou in "UO":
            r[f"1X&{ou}"] = u[f"H&{ou}"] + u[f"D&{ou}"]; r[f"12&{ou}"] = u[f"H&{ou}"] + u[f"A&{ou}"]; r[f"X2&{ou}"] = u[f"D&{ou}"] + u[f"A&{ou}"]
        out[f"{sc} DC&T{L}"] = {k: _wp(v) for k, v in r.items()}
        out[f"{sc} RES|T{L}"] = {f"{res} or {ou}": _wp(sum(X[i][j] for i in range(NMAX) for j in range(NMAX)
                                                           if _res(i - j) == res or ("O" if i + j > L else "U") == ou))
                                 for res in "HDA" for ou in "UO"}
    bt = lambda i, j: i > 0 and j > 0
    r = {f"{dc}&{g}": 0.0 for dc in ("1X", "12", "X2") for g in "YN"}
    for i in range(NMAX):
        for j in range(NMAX):
            g = "Y" if bt(i, j) else "N"; res = _res(i - j)
            if res in "HD": r[f"1X&{g}"] += X[i][j]
            if res in "HA": r[f"12&{g}"] += X[i][j]
            if res in "DA": r[f"X2&{g}"] += X[i][j]
    out[f"{sc} DC&BTTS"] = {k: _wp(v) for k, v in r.items()}
    out[f"{sc} RES|BTTS"] = {f"{res} or Y": _wp(sum(X[i][j] for i in range(NMAX) for j in range(NMAX) if _res(i - j) == res or bt(i, j))) for res in "HDA"}
    out[f"{sc} RES|ANYCS"] = {f"{res} or CS": _wp(sum(X[i][j] for i in range(NMAX) for j in range(NMAX) if _res(i - j) == res or i == 0 or j == 0)) for res in "HDA"}
    out[f"{sc} NDBTTS"] = _yes(sum(X[i][j] for i in range(NMAX) for j in range(NMAX) if bt(i, j) and i != j))
    wm = {"D": pd}
    for k in (1, 2): wm[f"H{k}"] = D.get(k, 0); wm[f"A{k}"] = D.get(-k, 0)
    wm["H3+"] = sum(p for d, p in D.items() if d >= 3); wm["A3+"] = sum(p for d, p in D.items() if d <= -3)
    out[f"{sc} WM"] = {k: _wp(v) for k, v in wm.items()}
    out[f"{sc} LASTGOAL"] = out[f"{sc} FIRSTGOAL"]
    out[f"{sc} HNB"] = {"D": (pd, ph, pa), "A": (pa, ph, pd)}
    out[f"{sc} ANB"] = {"H": (ph, pa, pd), "D": (pd, pa, ph)}
    out[f"{sc} WTN"] = {"H": _wp(sum(X[i][0] for i in range(1, NMAX))), "A": _wp(sum(X[0][j] for j in range(1, NMAX)))}
    out[f"{sc} WTS"] = {"None": _wp(A[0] * B[0]), "OnlyH": _wp(B[0] * (1 - A[0])), "OnlyA": _wp(A[0] * (1 - B[0])),
                        "Both": _wp((1 - A[0]) * (1 - B[0]))}
    if deep:
        S = _seq(lh, la)
        if S:
            out[f"{sc} FROMBEHIND H"] = _yes(S["fromBehindH"]); out[f"{sc} FROMBEHIND A"] = _yes(S["fromBehindA"])
    return X


def _crosshalf(l1h, l1a, l2h, l2a, lh, la, out, n=10):
    """Markets that need both halves jointly (independent Poisson halves)."""
    A1, B1, A2, B2 = _dist(l1h, n), _dist(l1a, n), _dist(l2h, n), _dist(l2a, n)
    htft_t = {}; htft_1h = {}; htft_ex = {}; dc_1hbtts = {}
    for i1 in range(n):
        for j1 in range(n):
            p1 = A1[i1] * B1[j1]; r1 = _res(i1 - j1); t1 = i1 + j1; b1 = "Y" if i1 and j1 else "N"
            for i2 in range(n):
                for j2 in range(n):
                    p = p1 * A2[i2] * B2[j2]; r2 = _res(i1 + i2 - j1 - j2); T = t1 + i2 + j2; k = f"{r1}/{r2}"
                    for L in (1.5, 2.5, 3.5, 4.5):
                        htft_t[(L, f"{k}&{'O' if T > L else 'U'}")] = htft_t.get((L, f"{k}&{'O' if T > L else 'U'}"), 0) + p
                    for L in (0.5, 1.5, 2.5):
                        key = (L, f"{k}&{'O' if t1 > L else 'U'}"); htft_1h[key] = htft_1h.get(key, 0) + p
                    key = f"{k}&{min(T, 7)}"; htft_ex[key] = htft_ex.get(key, 0) + p
                    for dc, ok in (("1X", r2 in "HD"), ("12", r2 in "HA"), ("X2", r2 in "DA")):
                        if ok: dc_1hbtts[f"{dc}&{b1}"] = dc_1hbtts.get(f"{dc}&{b1}", 0) + p
    for L in (1.5, 2.5, 3.5, 4.5):
        out[f"FT HTFT&T{L}"] = {o: _wp(v) for (l, o), v in htft_t.items() if l == L}
    for L in (0.5, 1.5, 2.5):
        out[f"FT HTFT&1HT{L}"] = {o: _wp(v) for (l, o), v in htft_1h.items() if l == L}
    out["FT HTFT&EXACT"] = {o: _wp(v) for o, v in htft_ex.items()}
    out["FT DC&1HBTTS"] = {o: _wp(v) for o, v in dc_1hbtts.items()}
    X1 = [[A1[i] * B1[j] for j in range(n)] for i in range(n)]; X2 = [[A2[i] * B2[j] for j in range(n)] for i in range(n)]
    D1, D2 = _diff(X1), _diff(X2); T1, T2 = _tot(X1), _tot(X2)
    h1 = sum(p for d, p in D1.items() if d > 0); h2 = sum(p for d, p in D2.items() if d > 0)
    a1 = sum(p for d, p in D1.items() if d < 0); a2 = sum(p for d, p in D2.items() if d < 0)
    out["FT WINBOTH H"] = _yes(h1 * h2); out["FT WINBOTH A"] = _yes(a1 * a2)
    out["FT WINEITHER H"] = _yes(1 - (1 - h1) * (1 - h2)); out["FT WINEITHER A"] = _yes(1 - (1 - a1) * (1 - a2))
    def hsh(d1, d2):
        g = sum(d1.get(i, 0) * d2.get(j, 0) for i in range(n) for j in range(n) if i > j)
        l = sum(d1.get(i, 0) * d2.get(j, 0) for i in range(n) for j in range(n) if i < j)
        return {"1H": _wp(g), "2H": _wp(l), "EQ": _wp(1 - g - l)}
    out["FT HSH"] = hsh(T1, T2)
    out["FT HSHH"] = hsh({i: A1[i] for i in range(n)}, {i: A2[i] for i in range(n)})
    out["FT HSHA"] = hsh({i: B1[i] for i in range(n)}, {i: B2[i] for i in range(n)})
    r = {}
    for x in "HDA":
        for y in "HDA":
            r.setdefault(x, 0.0)
    pr = {x: sum(p for d, p in D1.items() if _res(d) == x) for x in "HDA"}
    # "1st half result or match result": wins if the pick leads at half-time or wins the match
    X = _joint(lh, la); D = _diff(X)
    both = {x: 0.0 for x in "HDA"}
    for d1, p1 in D1.items():
        for d2, p2 in D2.items():
            if _res(d1) == _res(d1 + d2): both[_res(d1)] += p1 * p2
    full = {x: sum(p for d, p in D.items() if _res(d) == x) for x in "HDA"}
    out["FT HTORFT"] = {x: _wp(pr[x] + full[x] - both[x]) for x in "HDA"}
    # time of first goal (piecewise rate: FH share of goals in the first 45 min)
    lam = lh + la; ph = lh / lam if lam else 0.5
    def cum(t):                     # expected goals by minute t
        return lam * (FH * min(t, 45) / 45 + (1 - FH) * max(0, t - 45) / 45)
    for width, name in ((15, "FG15"), (10, "FG10")):
        o = {}; edges = list(range(0, 90, width)) + [90]
        for a, b in zip(edges[:-1], edges[1:]):
            o[f"{a + 1}-{b}"] = _wp(math.exp(-cum(a)) - math.exp(-cum(b)))
        o["None"] = _wp(math.exp(-cum(90)))
        out[f"FT {name}"] = o
    # 1st goal & 1X2 (first scorer H/A with final result), exact sequence argument
    res = {f"{f}&{x}": 0.0 for f in "HA" for x in "HDA"}
    pq = lh / lam if lam else 0.5
    for N in range(1, 14):
        wN = pois(N, lam)
        for f, pf in (("H", pq), ("A", 1 - pq)):
            for k in range(0, N):                           # k home goals among the other N-1
                pb = math.comb(N - 1, k) * pq ** k * (1 - pq) ** (N - 1 - k)
                hg = k + (1 if f == "H" else 0); ag = (N - 1 - k) + (1 if f == "A" else 0)
                res[f"{f}&{_res(hg - ag)}"] += wN * pf * pb
    out["FT FIRSTGOAL&1X2"] = {k: _wp(v) for k, v in res.items()}

def price_book(lh, la, deep=True):
    out = {}
    _half_block("FT", lh, la, out, deep)
    l1h, l1a = lh * FH, la * FH; l2h, l2a = lh * (1 - FH), la * (1 - FH)
    X1 = _half_block("1H", l1h, l1a, out, False)
    # halves are independent in the model
    X2 = _joint(l2h, l2a); T1, T2 = _tot(X1), _tot(X2); D1, D2 = _diff(X1), _diff(X2)
    A1, B1, A2, B2 = _dist(l1h), _dist(l1a), _dist(l2h), _dist(l2a)
    out["FT HTFT"] = {}
    for r1 in "HDA":
        for r2 in "HDA":
            pr = sum(p1 * p2 for d1, p1 in D1.items() if _res(d1) == r1 for d2, p2 in D2.items() if _res(d1 + d2) == r2)
            out["FT HTFT"][f"{r1}/{r2}"] = _wp(pr)
    g1, g2 = 1 - T1[0], 1 - T2[0]
    _crosshalf(l1h, l1a, l2h, l2a, lh, la, out)
    _half_block("2H", l2h, l2a, out, False)
    out["FT GOALBOTHHALVES"] = _yes(g1 * g2)
    out["FT BOTHHALVES O1.5"] = _yes((1 - T1[0] - T1[1]) * (1 - T2[0] - T2[1]))
    out["FT BOTHHALVES U1.5"] = _yes((T1[0] + T1[1]) * (T2[0] + T2[1]))
    b1, b2 = (1 - A1[0]) * (1 - B1[0]), (1 - A2[0]) * (1 - B2[0])
    out["FT GGNG HALVES"] = {"N/N": _wp((1 - b1) * (1 - b2)), "Y/N": _wp(b1 * (1 - b2)), "N/Y": _wp((1 - b1) * b2), "Y/Y": _wp(b1 * b2)}
    out["FT BTTSBOTHHALVES"] = _yes(b1 * b2)
    out["FT HSCOREBOTH"] = _yes((1 - A1[0]) * (1 - A2[0])); out["FT ASCOREBOTH"] = _yes((1 - B1[0]) * (1 - B2[0]))
    if deep:
        S = _seq(lh, la)
        if S:
            out["FT 1X2-1UP"] = {"H": _wp(S["leadH1"]), "D": _wp(S["draw"]), "A": _wp(S["leadA1"])}
            out["FT 1X2-2UP"] = {"H": _wp(S["2upH_or_win"]), "D": _wp(S["draw"]), "A": _wp(S["2upA_or_win"])}
            out["FT 1X2-NEVERDOWN"] = {"H": _wp(S["neverDownH"]), "D": _wp(S["draw"]), "A": _wp(S["neverDownA"])}
            out["FT DC-1UP"] = {"1X": _wp(S["1upH_or_draw"]), "X2": _wp(S["1upA_or_draw"])}
            for x in (1, 2, 3):
                out[f"FT LEADANY {x}"] = _yes(S[f"leadAny{x}"]); out[f"FT LEADH {x}"] = _yes(S[f"leadH{x}"]); out[f"FT LEADA {x}"] = _yes(S[f"leadA{x}"])
            for x in (2, 3):
                out[f"FT ROWANY {x}"] = _yes(S[f"rowAny{x}"]); out[f"FT ROWH {x}"] = _yes(S[f"rowH{x}"]); out[f"FT ROWA {x}"] = _yes(S[f"rowA{x}"])
        S1 = _seq(l1h, l1a, 8)
        if S1: out["1H FROMBEHIND H"] = _yes(S1["fromBehindH"]); out["1H FROMBEHIND A"] = _yes(S1["fromBehindA"])
    return out

def eff(w, p, l, odds):
    """Return (expected value per unit staked, win-equivalent probability) for a bet priced at `odds`."""
    ev = w * (odds - 1) - l
    return ev, (ev + 1) / odds

def scan(lh, la, book, minP=0.60, minE=0.03, minO=1.15, gap=0.12, wm=0.6):
    """book: {key: {outcome: odds}}. A complete outcome set with no pushes is blended 60/40 with the
    margin-free market price; Asian/push lines and one-sided markets are model-only (flag 'model only')."""
    P = price_book(lh, la); rows = []
    for key, outs in book.items():
        if key not in P: continue
        model = P[key]; complete = set(outs) == set(model) and all(model[o][1] < 1e-9 for o in model)
        if complete and len(model) <= 3:
            q = {o: 1 / v for o, v in outs.items()}; tq = sum(q.values())
        for o, v in outs.items():
            if o not in model: continue
            w, p, l = model[o]; ev, mp = eff(w, p, l, v)
            if complete and len(model) <= 3:
                fair = q[o] / tq; bl = wm * mp + (1 - wm) * fair; g = abs(mp - fair)
                edge = bl * v - 1; tag = ""
            else:
                fair = None; bl = mp; g = 0.0; edge = ev; tag = "model only"
            ok = bl >= minP and edge >= minE and v >= minO and g <= gap
            st = "PICK" if ok else ("CHECK DATA" if (bl >= minP and edge >= minE and g > gap) else "-")
            rows.append(dict(market=key, outcome=o, odds=v, model=mp, fair=fair, blended=bl, edge=edge, gap=g, status=st, note=tag))
    return sorted(rows, key=lambda r: -r["edge"])

def fit_lambdas(book, start=(1.5, 1.0)):
    """Market-implied (lh, la): least-squares fit of the model to margin-free prices of the complete markets."""
    import itertools
    keys = [k for k in book if k.startswith("FT") and any(t in k for t in (" 1X2", " OU ", " BTTS", " TTH ", " TTA ", " DC", " AH "))]
    def err(lh, la):
        P = price_book(lh, la, deep=False); e = 0.0
        for k in keys:
            outs = book[k]
            if k not in P or set(outs) != set(P[k]): continue
            q = {o: 1 / v for o, v in outs.items()}; tq = sum(q.values())
            if len(P[k]) == 3 and k.endswith("DC"): continue
            for o in outs:
                if P[k][o][1] > 1e-9: continue
                e += (P[k][o][0] - q[o] / tq) ** 2
        return e
    lh, la = start; step = 0.4; best = err(lh, la)
    for _ in range(40):
        moved = False
        for dh, da in itertools.product((-step, 0, step), repeat=2):
            if dh == da == 0: continue
            a, b = max(0.05, lh + dh), max(0.05, la + da); e = err(a, b)
            if e < best - 1e-12: best, lh, la, moved = e, a, b, True
        if not moved: step /= 2
        if step < 1e-4: break
    return lh, la, best


def evaluate_all(m, book, S=None):
    """Full pipeline: match data dict -> model lambdas (form, injuries, H2H, Elo...) -> scan the whole book."""
    import model as M
    S = S or M.DEFAULTS
    lam = M.lambdas(m, S)
    if not lam: return None
    return lam, scan(lam[0], lam[1], book, S["minP"], S["minE"], S["minO"], S["gap"])
