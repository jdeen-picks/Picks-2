/* Match Model core - same maths as Betting_Model.xlsx */
var MM = (function () {
  var MARKETS = ["Home win","Draw","Away win","Home or Draw","Draw or Away","Home or Away","Draw No Bet Home","Draw No Bet Away",
    "Over 1.5","Under 1.5","Over 2.5","Under 2.5","Over 3.5","Under 3.5","BTTS Yes","BTTS No"];
  var DEFAULTS = {wf:0.5,k:6,ref:1.35,ia:0.04,im:0.02,id:0.04,minA:0.75,maxD:1.35,h2w:0.10,h2t:0.06,trust:0.60,minE:0.03,minP:0.55,minO:1.15,gap:0.15,lo:1.90,hi:2.30,stake:15};
  var LEAGUES = {"European games (no adjustment)":[1.45,1.20,1.00],"Europa League":[1.45,1.20,1.00],"Conference League":[1.45,1.20,1.00],
    "Champions League":[1.55,1.25,1.00],"England":[1.55,1.25,1.00],"Spain":[1.45,1.10,1.00],"Germany":[1.70,1.35,1.00],"Italy":[1.40,1.15,1.00],
    "France":[1.50,1.20,0.97],"Portugal":[1.45,1.10,0.90],"Netherlands":[1.70,1.35,0.90],"Belgium":[1.55,1.25,0.88],"Turkey":[1.55,1.25,0.88],
    "Scotland":[1.55,1.25,0.82],"Austria":[1.60,1.30,0.82],"Switzerland":[1.65,1.35,0.82],"Greece":[1.30,1.00,0.82],"Czechia":[1.60,1.25,0.82],
    "Poland":[1.55,1.25,0.80],"Norway":[1.75,1.40,0.80],"Denmark":[1.55,1.25,0.82],"Croatia":[1.50,1.20,0.78],"Israel":[1.45,1.15,0.75],
    "Bulgaria":[1.45,1.15,0.72],"Cyprus":[1.50,1.20,0.72],"Qatar / Gulf":[1.60,1.25,0.78],"Ghana":[1.05,0.75,0.60],"Other league":[1.45,1.15,0.80]};
  function N(x){ x = Number(x); return isFinite(x) ? x : 0; }
  function has(x){ return x !== null && x !== undefined && x !== "" && isFinite(Number(x)); }
  function pois(k, l){ var p = Math.exp(-l); for (var i = 1; i <= k; i++) p *= l / i; return p; }
  function pcum(k, l){ var s = 0; for (var i = 0; i <= k; i++) s += pois(i, l); return s; }
  function lambdas(m, S, L) {
    L = L || LEAGUES;
    var comp = L[m.comp], hl = L[m.hlg], al = L[m.alg];
    if (!m.home || !m.away || !comp || !hl || !al || !(N(m.h_nf) > 0) || !(N(m.a_nf) > 0) ||
        !has(m.h_gff) || !has(m.h_gaf) || !has(m.a_gff) || !has(m.a_gaf)) return null;
    var Lh = comp[0], La = comp[1], res = {};
    function side(p, sf) {
      var useS = N(m[p+"_ns"]) > 0 && has(m[p+"_gfs"]) && has(m[p+"_gas"]);
      var gf = useS ? S.wf*N(m[p+"_gff"]) + (1-S.wf)*N(m[p+"_gfs"]) : N(m[p+"_gff"]);
      var ga = useS ? S.wf*N(m[p+"_gaf"]) + (1-S.wf)*N(m[p+"_gas"]) : N(m[p+"_gaf"]);
      var ne = useS ? S.wf*N(m[p+"_nf"]) + (1-S.wf)*N(m[p+"_ns"]) : N(m[p+"_nf"]);
      return {att: ((ne*(gf*sf)+S.k*S.ref)/(ne+S.k))/S.ref, def: ((ne*(ga/sf)+S.k*S.ref)/(ne+S.k))/S.ref};
    }
    var h = side("h", hl[2]), a = side("a", al[2]);
    function inj(ip){
      return {att: Math.max(S.minA, 1-(S.ia*N(m[ip+"_att"])+S.im*N(m[ip+"_mid"]))),
              def: Math.min(S.maxD, 1+S.id*N(m[ip+"_def"])+S.im*N(m[ip+"_mid"]))};
    }
    var hi = inj("hi"), ai = inj("ai");
    var lh0 = Lh*h.att*a.def*hi.att*ai.def*(1+N(m.h_mot));
    var la0 = La*a.att*h.def*ai.att*hi.def*(1+N(m.a_mot));
    var tf = 1;
    if (N(m.h2h_n) > 0 && N(m.h2h_tot) > 0)
      tf = Math.max(0.9, Math.min(1.1, 1 + S.h2w*(Math.min(N(m.h2h_n),5)/5)*(N(m.h2h_tot)/(lh0+la0) - 1)));
    var tilt = N(m.h2h_n) <= 0 ? 0 : Math.max(-0.08, Math.min(0.08, S.h2t*(N(m.h2h_w)-N(m.h2h_l))/N(m.h2h_n)));
    function cl(x){ return Math.max(0.15, Math.min(4.5, x)); }
    return {h: cl(lh0*tf*(1+tilt)), a: cl(la0*tf*(1-tilt))};
  }
  function probs(lh, la) {
    var ph = 0, pd = 0, i, j;
    for (i = 0; i <= 10; i++) for (j = 0; j <= 10; j++) {
      var p = pois(i, lh)*pois(j, la);
      if (i > j) ph += p; else if (i === j) pd += p;
    }
    // match workbook: home = sum P(h=i)*P(away<=i-1) up to 10, draw = sum P(h=i)P(a=i)
    ph = 0; pd = 0;
    for (i = 1; i <= 10; i++) ph += pois(i, lh)*pcum(i-1, la);
    for (i = 0; i <= 10; i++) pd += pois(i, lh)*pois(i, la);
    var pa = 1-ph-pd, t = lh+la, o15 = 1-pcum(1,t), o25 = 1-pcum(2,t), o35 = 1-pcum(3,t), bt = (1-Math.exp(-lh))*(1-Math.exp(-la));
    return [ph,pd,pa,ph+pd,pd+pa,ph+pa,ph/(ph+pa),pa/(ph+pa),o15,1-o15,o25,1-o25,o35,1-o35,bt,1-bt];
  }
  function marketProbs(o) {
    var r = new Array(16).fill(null), c3 = has(o[0]) && has(o[1]) && has(o[2]);
    if (c3) {
      var s = 1/o[0]+1/o[1]+1/o[2]; r[0]=(1/o[0])/s; r[1]=(1/o[1])/s; r[2]=(1/o[2])/s;
      r[3]=r[0]+r[1]; r[4]=r[1]+r[2]; r[5]=r[0]+r[2]; r[6]=r[0]/(r[0]+r[2]); r[7]=r[2]/(r[0]+r[2]);
    }
    [[8,9],[10,11],[12,13],[14,15]].forEach(function (p) {
      if (has(o[p[0]]) && has(o[p[1]])) { r[p[0]] = (1/o[p[0]])/(1/o[p[0]]+1/o[p[1]]); r[p[1]] = 1-r[p[0]]; }
    });
    return r;
  }
  function evaluate(m, odds, S, L) {
    var lam = lambdas(m, S, L);
    if (!lam) return {status: "Missing data", pick: null, markets: []};
    var mod = probs(lam.h, lam.a), mk = marketProbs(odds), check = false;
    if (mk[0] !== null) check = Math.max(Math.abs(mod[0]-mk[0]), Math.abs(mod[1]-mk[1]), Math.abs(mod[2]-mk[2])) > S.gap;
    var rows = [], best = null;
    for (var k = 0; k < 16; k++) {
      if (!has(odds[k])) continue;
      var o = Number(odds[k]), bl = mk[k] === null ? mod[k] : S.trust*mod[k] + (1-S.trust)*mk[k], edge = bl*o-1;
      var ok = !check && o >= S.minO && bl >= S.minP && edge >= S.minE && (mk[k] === null || Math.abs(mod[k]-mk[k]) <= S.gap);
      var row = {name: MARKETS[k], odds: o, model: mod[k], market: mk[k], blended: bl, edge: edge, eligible: ok};
      rows.push(row);
      if (ok && (!best || edge > best.edge)) best = row;
    }
    return {status: check ? "CHECK DATA" : "OK", lam: lam, pick: best, markets: rows, total: lam.h+lam.a};
  }
  function bestSlip(picks, S) {
    var best = null;
    for (var i = 0; i < picks.length; i++) for (var j = i+1; j < picks.length; j++) {
      var o = picks[i].odds*picks[j].odds, p = picks[i].blended*picks[j].blended;
      if (o >= S.lo && o <= S.hi && (!best || p > best.p)) best = {a: picks[i], b: picks[j], odds: o, p: p};
    }
    return best;
  }
  return {MARKETS:MARKETS, DEFAULTS:DEFAULTS, LEAGUES:LEAGUES, lambdas:lambdas, probs:probs, evaluate:evaluate, bestSlip:bestSlip, has:has};
})();
if (typeof module !== "undefined") module.exports = MM;
