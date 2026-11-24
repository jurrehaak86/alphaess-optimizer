"""Rekenkern: dynamic programming over de SoC, per kwartier.

Overgenomen uit accu_optimizer.py (pyscript, live versie 11-11-2026). De functies
accu_plan, accu_plan_intern, accu_plan_eigen en kwantiel zijn ongewijzigd, alleen
zonder @pyscript_compile. verkoopprijs krijgt de salderingsaftrek als parameter.
Geen Home Assistant-imports: ook bruikbaar in de backtest.
"""
from __future__ import annotations

def accu_plan(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, reserve0, used_today,
              limit_kwh, pq, eta, step, res_factor, tv, allow_hold, tiebreak=1e-5,
              hold_at_plafond=True, reserve_reeks=None, limiet_morgen=True, wear=0.0, exp_pen=0.0,
              allowed=None, lcap=None, doel_kwh=None, doel_straf=0.0):
    """Plan over de horizon. Alle reeksen per kwartier, index 0 = huidig kwartier.

    buy/sell: EUR/kWh all-in; load: kWh huisverbruik; dag: 0 = vandaag, 1 = morgen.
    soc0, floor_kwh, plafond_kwh, reserve0: kWh in de accu.
    used_today: al ontladen kWh (AC) vandaag; limit_kwh: daglimiet of None.
    tv: waarde (EUR) per kWh restlading aan het einde van de horizon.
    wear: slijtagekosten (EUR) per kWh die uit de accu komt.
    doel_kwh/doel_straf: zachte streefwaarde (backup). Elk kwartier kost elke kWh die de
    accu ONDER doel_kwh zit doel_straf EUR (alleen in de afweging, niet in 'kosten').
    hold_at_plafond: True = 'laden' op/boven het plafond houdt de accu stil (net voedt
    huis); False = valt terug op balans. Moet overeenkomen met wat v4 dan doet.
    reserve_reeks: optioneel de reserve per kwartier (anders afbouw vanaf reserve0).
    Acties: 'L' laden (net -> accu, tot plafond), 'O' ontladen (accu -> huis + net,
    tot reserve), 'B' balans (accu voedt huis tot vloer), 'H' vasthouden (optioneel).
    """
    n = len(buy)
    acts = ['B', 'L', 'O'] + (['H'] if allow_hold else [])
    # reserve in het plan: bouwt af met het verwachte verbruik (x factor), nooit onder vloer
    res = [0.0] * n
    cum = 0.0
    for t in range(n):
        r = reserve0 - res_factor * cum if reserve_reeks is None else reserve_reeks[t]
        res[t] = r if r > floor_kwh else floor_kwh
        cum += load[t]
    top = max(soc0, plafond_kwh, floor_kwh)
    K = int((top - floor_kwh) / step + 0.999999) + 1
    lev = [floor_kwh + k * step for k in range(K)]
    smax = lev[-1]

    def trans(s, a, t):
        """-> (s_next, ontladen_ac, netto_net). netto > 0 = afname."""
        ld = load[t]
        if a == 'L':
            room = (plafond_kwh - s) / eta
            if lcap is not None and lcap[t] < room:
                room = lcap[t]
            if room > 1e-9 or hold_at_plafond:
                c = pq if pq < room else room
                if c < 0:
                    c = 0.0
                return s + c * eta, 0.0, ld + c
            a = 'B'   # accu op plafond en v4 valt dan terug op balans
        if a == 'O':
            avail = (s - res[t]) * eta
            if avail >= ld and avail > 0:
                d = pq if pq < avail else avail
                return s - d / eta, d, ld - d
            a = 'B'
        if a == 'B':
            avail = (s - floor_kwh) * eta
            if avail < 0:
                avail = 0.0
            d = ld if ld < avail else avail
            return s - d / eta, d, ld - d
        return s, 0.0, ld  # 'H'

    def interp(J, s):
        x = (s - floor_kwh) / step
        if x <= 0:
            return J[0] + x * (J[1] - J[0]) if K > 1 else J[0]
        i = int(x)
        if i >= K - 1:
            return J[K - 1] + (x - (K - 1)) * (J[K - 1] - J[K - 2]) if K > 1 else J[0]
        f = x - i
        return J[i] + f * (J[i + 1] - J[i])

    def solve(lam0, lam1):
        Js = [None] * (n + 1)
        Js[n] = [-tv * s for s in lev]
        for t in range(n - 1, -1, -1):
            Jn = Js[t + 1]
            b = buy[t]; sl = sell[t]
            lam = lam0 if dag[t] == 0 else lam1
            row = [0.0] * K
            for k in range(K):
                s = lev[k]
                best = 1e18
                for a in (acts if allowed is None else allowed[t]):
                    s2, d, net = trans(s, a, t)
                    c = b * net if net > 0 else sl * net - exp_pen * net
                    c += (lam + wear) * d
                    if a == 'L' or a == 'O':
                        c += tiebreak * (d if d > 0 else net - load[t])
                    if doel_straf > 0 and s2 < doel_kwh:
                        c += doel_straf * (doel_kwh - s2)
                    v = c + interp(Jn, s2)
                    if v < best:
                        best = v
                row[k] = best
            Js[t] = row
        # vooruit vanaf de echte SoC
        s = soc0
        out_a = []; out_s = []; out_net = []
        dis = [0.0, 0.0]
        tot = 0.0
        for t in range(n):
            lam = lam0 if dag[t] == 0 else lam1
            best = 1e18; ba = 'B'; bs = s; bd = 0.0; bn = 0.0; bc = 0.0
            for a in (acts if allowed is None else allowed[t]):
                s2, d, net = trans(s, a, t)
                c = buy[t] * net if net > 0 else sell[t] * net
                pen = (lam + wear) * d + (0.0 if net > 0 else -exp_pen * net)
                if a == 'L' or a == 'O':
                    pen += tiebreak * (d if d > 0 else net - load[t])
                if doel_straf > 0 and s2 < doel_kwh:
                    pen += doel_straf * (doel_kwh - s2)
                v = c + pen + interp(Js[t + 1], s2)
                if v < best - 1e-12:
                    best = v; ba = a; bs = s2; bd = d; bn = net; bc = c
            if ba == 'O' and bd <= load[t] + 1e-9:
                ba = 'B'  # ontladen dat niets exporteert is balans
            if ba == 'L' and bs <= s + 1e-9:
                # 'laden' op het plafond laadt niets: vasthouden, of balans als v4 dan balanceert
                ba = 'H' if hold_at_plafond else 'B'
            out_a.append(ba); out_s.append(bs); out_net.append(bn)
            dis[0 if dag[t] == 0 else 1] += bd
            tot += bc
            s = bs
        return out_a, out_s, out_net, dis, tot

    # Cycluslimiet via Lagrange-straf per kWh ontladen, gebisect tot de limiet past.
    # Eerst morgen (lam1), daarna vandaag (lam0) met lam1 vast: het besluit voor NU
    # respecteert de limiet altijd; morgen wordt morgen opnieuw exact afgedwongen.
    lam0 = 0.0; lam1 = 0.0
    res_ = solve(0.0, 0.0)
    runs = 1
    if limit_kwh is not None:
        left0 = limit_kwh - used_today
        if left0 < 0:
            left0 = 0.0
        if limiet_morgen and (1 in dag) and res_[3][1] > limit_kwh + 1e-6:
            lo, hi, best = 0.0, 0.6, None
            for _ in range(8):
                mid = 0.5 * (lo + hi)
                r = solve(0.0, mid); runs += 1
                if r[3][1] > limit_kwh + 1e-6:
                    lo = mid
                else:
                    hi = mid; best = r
            lam1 = hi
            res_ = best if best is not None else solve(0.0, hi)
            runs += 0 if best is not None else 1
        if res_[3][0] > left0 + 1e-6:
            lo, hi, best = 0.0, 1.0, None
            for _ in range(9):
                mid = 0.5 * (lo + hi)
                r = solve(mid, lam1); runs += 1
                if r[3][0] > left0 + 1e-6:
                    lo = mid
                else:
                    hi = mid; best = r
            lam0 = hi
            if best is None:
                best = solve(hi, lam1); runs += 1
            res_ = best
    a, s, net, dis, tot = res_
    return {'acties': a, 'soc': s, 'net': net, 'ontladen_dag': dis, 'kosten': tot,
            'lambda': [lam0, lam1], 'dp_runs': runs, 'reserve_plan': res}


def accu_plan_intern(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, used_today, limit_kwh,
                     pq, eta, step, res_factor, tv, allow_hold, tiebreak=1e-5,
                     hold_at_plafond=True, limiet_morgen=True, wear=0.0, exp_pen=0.0,
                     doel_kwh=None, doel_straf=0.0):
    """Twee rondes. 1) plan zonder reserve -> waar laadt het plan? 2) reserve per kwartier =
    vloer + res_factor x verbruik tot het volgende laadkwartier, en daarmee opnieuw plannen.
    Zo blijft er genoeg staan voor eigen verbruik tot het volgende laadmoment, maar springt de
    reserve niet naar 100% op dagen zonder 'laadblok'."""
    n = len(buy)
    p1 = accu_plan(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, floor_kwh, used_today,
                   limit_kwh, pq, eta, step, res_factor, tv, allow_hold, tiebreak, hold_at_plafond,
                   [floor_kwh] * n, limiet_morgen, wear, exp_pen, None, None, doel_kwh, doel_straf)
    acts = p1['acties']
    res = [floor_kwh] * n
    acc = 0.0
    for t in range(n - 1, -1, -1):
        if acts[t] == 'L':
            acc = 0.0
        else:
            acc += load[t]
        r = floor_kwh + res_factor * acc
        res[t] = r if r < plafond_kwh else plafond_kwh
    p2 = accu_plan(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, res[0], used_today,
                   limit_kwh, pq, eta, step, res_factor, tv, allow_hold, tiebreak, hold_at_plafond,
                   res, limiet_morgen, wear, exp_pen, None, None, doel_kwh, doel_straf)
    p2['dp_runs'] = p2['dp_runs'] + p1['dp_runs']
    return p2


def accu_plan_eigen(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, used_today, limit_kwh,
                    pq, eta, step, res_factor, tv, allow_hold, tiebreak=1e-5,
                    hold_at_plafond=True, limiet_morgen=True, wear=0.0, exp_pen=0.0,
                    reserve_extern=None, doel_kwh=None, doel_straf=0.0,
                    hold_vrij=False, marge_vast=False, ext_factor=None, min_verkoop=0.0,
                    ext_schaal=False):
    """Eigen verbruik eerst (wens Jurre 27-10-2026), als harde regels:
    A) plan ZONDER verkoop: alleen balans, laden en vasthouden. Laden gebeurt dus alleen als
       het goedkoper is dan het latere eigen verbruik dat het dekt.
    B) daarna mag er alleen verkocht worden wat boven de reserve ligt (verbruik tot het
       volgende laadkwartier van A, x res_factor). Laden mag nooit meer dan in A (geen inkoop
       om te verkopen) en vasthouden alleen waar A ook vasthield (nooit vasthouden om te
       verkopen ten koste van eigen verbruik)."""
    n = len(buy)
    zonder_o = [('BLH' if allow_hold else 'BL')] * n
    pa = accu_plan(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, floor_kwh, used_today,
                   limit_kwh, pq, eta, step, res_factor, tv, allow_hold, tiebreak, hold_at_plafond,
                   [floor_kwh] * n, limiet_morgen, wear, exp_pen, zonder_o, None, doel_kwh, doel_straf)
    acts = pa['acties']; soc = pa['soc']
    lcap = [0.0] * n
    prev = soc0
    for t in range(n):
        if acts[t] == 'L':
            lcap[t] = max(0.0, (soc[t] - prev) / eta) + 1e-6
        prev = soc[t]
    # verbruik dat de accu zelf moet dekken tot het volgende laadkwartier van ronde A.
    # hold_vrij (11-11-2026): kwartieren waarin A vasthoudt tellen niet mee; daar voedt het
    # net het huis, dus die stroom hoeft niet in de accu te blijven.
    accs = [0.0] * n
    acc = 0.0
    for t in range(n - 1, -1, -1):
        if acts[t] == 'L':
            acc = 0.0
        elif not (hold_vrij and acts[t] == 'H'):
            acc += load[t]
        accs[t] = acc
    res = [floor_kwh] * n
    marge = 0.0
    for t in range(n):
        if marge_vast:
            # vaste marge per blok tussen twee laadmomenten (11-11-2026): de reserve zakt dan
            # 1-op-1 mee met het verbruik, de ruimte boven de reserve blijft gelijk en de
            # verkoop belandt in het duurste kwartier i.p.v. steeds later op de avond.
            if t == 0 or acts[t - 1] == 'L':
                marge = (res_factor - 1.0) * accs[t]
            r = floor_kwh + accs[t] + marge
        else:
            r = floor_kwh + res_factor * accs[t]
        res[t] = r if r < plafond_kwh else plafond_kwh
    toegestaan = []
    for t in range(n):
        a = 'BO'
        if acts[t] == 'L':
            a += 'L'
        if acts[t] == 'H':
            a += 'H'
        toegestaan.append(a)
    if reserve_extern is not None:
        # verkoopvloer = de HOOGSTE van: reserve-sensor (afbouwend met verbruik) en het eigen
        # verbruik tot het volgende laadmoment uit ronde A. Zo wordt nooit stroom verkocht die
        # het huis later (vóór het volgende laadmoment) zelf nodig heeft.
        cum = 0.0
        eerste_l = n
        for t in range(n):
            if acts[t] == 'L':
                eerste_l = t
                break
        for t in range(n):
            if ext_schaal:
                # ext_schaal (11-11-2026): de reserve-sensor (p80 + marge) krimpt in dezelfde
                # verhouding als het resterende eigen verbruik tot het volgende laadmoment, in
                # plaats van met 1,2 x het GEMIDDELDE verbruik. Zo blijft de veiligheid van de
                # sensor behouden en komt er 's avonds ruimte vrij in de duurste kwartieren.
                if t >= eerste_l or accs[0] <= 1e-9:
                    break
                r = floor_kwh + (reserve_extern - floor_kwh) * accs[t] / accs[0]
            else:
                r = reserve_extern - (res_factor if ext_factor is None else ext_factor) * cum
            if r > res[t]:
                res[t] = r if r < plafond_kwh else plafond_kwh
            cum += load[t]
    pb = accu_plan(buy, sell, load, dag, soc0, floor_kwh, plafond_kwh, res[0], used_today,
                   limit_kwh, pq, eta, step, res_factor, tv, allow_hold, tiebreak, hold_at_plafond,
                   res, limiet_morgen, wear, exp_pen, toegestaan, lcap, doel_kwh, doel_straf)
    pb['dp_runs'] = pb['dp_runs'] + pa['dp_runs']
    if min_verkoop > 0:
        # minimale verkoop (11-11-2026): een ontlaadkwartier dat minder dan min_verkoop kWh
        # naar het net stuurt is een afrondingsrestje van het SoC-raster -> balans.
        for k in range(n):
            if pb['acties'][k] == 'O' and -pb['net'][k] < min_verkoop:
                pb['acties'][k] = 'B'
    return pb


def kwantiel(vals, q):
    v = sorted(vals)
    if not v:
        return 0.0
    x = q * (len(v) - 1)
    i = int(x)
    if i >= len(v) - 1:
        return v[-1]
    return v[i] + (x - i) * (v[i + 1] - v[i])



def verkoopprijs(inkoop, regime, eb, btw, verg_in, verg_uit, saldering_aftrek):
    """Verkoopprijs uit de all-in inkoopprijs.

    regime '2027': geen saldering, spot min verkoopvergoeding.
    regime '2026': saldering, teruglevering = all-in prijs min een vast bedrag.
    """
    if str(regime).startswith("2027"):
        spot = (inkoop / btw - eb) - verg_in
        return spot - verg_uit
    return inkoop - saldering_aftrek
