"""Van ruwe invoer naar een plan. Puur Python, geen Home Assistant-imports.

Dit is de HA-laag van accu_optimizer.py (pyscript) zonder state-lezen: de coordinator
verzamelt de invoer, deze module rekent en geeft een dict terug voor de entities.
Draait in een executor-thread.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import optimizer as kern
from .const import (
    ACTIONS,
    AGGRESSIVENESS_TABLE,
    BACKUP_PENALTY_PER_WEIGHT,
    HOLD_AT_CEILING,
    MIN_SELL_KWH,
    RESERVE_FACTOR,
    RESERVE_HOLD_FREE,
    RESERVE_MARGIN_FIXED,
    SOC_STEP_KWH,
    TIEBREAK,
)


@dataclass
class PlanInput:
    """Alles wat één planronde nodig heeft."""

    now: datetime
    prices: list[tuple[datetime, float]]   # (start kwartier, all-in inkoopprijs EUR/kWh)
    soc_pct: float
    capacity_kwh: float
    ceiling_pct: float
    floor_pct: float
    power_kw: float
    eta: float
    load_weekday: list[float]              # kWh per kwartier, 24 waarden (per uur van de dag)
    load_weekend: list[float]
    discharged_today_kwh: float
    regime: str
    energy_tax: float
    vat: float
    fee_in: float
    fee_out: float
    netting_deduction: float
    wear: float
    aggressiveness: int
    backup_target_pct: float
    backup_weight: float
    tomorrow_known: bool = False
    extra: dict = field(default_factory=dict)


def settings_for(level: int) -> dict:
    """Instellingen bij een agressiviteitsniveau (dichtstbijzijnde lagere rij)."""
    level = max(1, min(10, int(level)))
    row = AGGRESSIVENESS_TABLE[max(k for k in AGGRESSIVENESS_TABLE if k <= level)]
    return {"level": level, "strategy": row[0], "threshold": row[1], "end_quantile": row[2],
            "cycle_limit": row[3], "hold": row[4]}


def make_plan(inp: PlanInput) -> dict:
    """Bereken het plan. Geeft een dict met actie, reden, plan en diagnostiek."""
    kw_start = inp.now.replace(minute=(inp.now.minute // 15) * 15, second=0, microsecond=0)
    series = sorted((p for p in inp.prices if p[0] >= kw_start - timedelta(minutes=1)),
                    key=lambda x: x[0])
    if not series:
        return {"action": "balance", "reason": "no_prices"}

    cap = inp.capacity_kwh
    floor_kwh = inp.floor_pct / 100.0 * cap
    soc = inp.soc_pct / 100.0 * cap
    ceiling = max(floor_kwh, min(100.0, inp.ceiling_pct) / 100.0 * cap)

    buy = [v for _, v in series]
    sell = [kern.verkoopprijs(v, inp.regime, inp.energy_tax, inp.vat, inp.fee_in, inp.fee_out,
                              inp.netting_deduction) for v in buy]
    load = [(inp.load_weekend if st.weekday() >= 5 else inp.load_weekday)[st.hour]
            for st, _ in series]
    today = kw_start.date()
    day = [0 if st.date() == today else 1 for st, _ in series]

    cfg = settings_for(inp.aggressiveness)
    limit = None if cfg["cycle_limit"] is None else cfg["cycle_limit"] * cap
    tv = inp.eta * kern.kwantiel(buy, cfg["end_quantile"])
    target_kwh = inp.backup_target_pct / 100.0 * cap
    penalty = inp.backup_weight * BACKUP_PENALTY_PER_WEIGHT
    pq = inp.power_kw / 4.0

    if cfg["strategy"] == "eigen_verbruik_eerst":
        # reserve intern: verbruik tot het volgende laadmoment uit het eigen plan
        plan = kern.accu_plan_eigen(
            buy, sell, load, day, soc, floor_kwh, ceiling, inp.discharged_today_kwh, limit,
            pq, inp.eta, SOC_STEP_KWH, RESERVE_FACTOR, tv, cfg["hold"], TIEBREAK,
            HOLD_AT_CEILING, True, inp.wear, cfg["threshold"], None, target_kwh, penalty,
            RESERVE_HOLD_FREE, RESERVE_MARGIN_FIXED, None, MIN_SELL_KWH, False)
    else:
        plan = kern.accu_plan_intern(
            buy, sell, load, day, soc, floor_kwh, ceiling, inp.discharged_today_kwh, limit,
            pq, inp.eta, SOC_STEP_KWH, RESERVE_FACTOR, tv, cfg["hold"], TIEBREAK,
            HOLD_AT_CEILING, True, inp.wear, cfg["threshold"], target_kwh, penalty)

    acts = plan["acties"]
    a0 = acts[0]
    reserve_pct = round(100.0 * plan["reserve_plan"][0] / cap, 1)
    if a0 == "L":
        reason = f"charge: {buy[0] * 100:.1f} ct is cheap compared to later in the horizon"
    elif a0 == "O":
        reason = f"discharge: selling at {sell[0] * 100:.1f} ct pays off above reserve {reserve_pct:.0f}%"
    elif a0 == "H":
        reason = "hold: the stored energy is worth more later"
    else:
        reason = "balance: battery supplies the house"
    if limit is not None and plan["lambda"][0] > 0:
        reason += f" (cycle limit binding, λ={plan['lambda'][0] * 100:.1f} ct/kWh)"

    blocks: list[dict] = []
    for i, (st, _) in enumerate(series):
        a = ACTIONS[acts[i]]
        end = (st + timedelta(minutes=15)).isoformat()
        soc_end = round(100 * plan["soc"][i] / cap)
        if blocks and blocks[-1]["action"] == a:
            blocks[-1]["to"] = end
            blocks[-1]["soc_end"] = soc_end
        else:
            blocks.append({"from": st.isoformat(), "to": end, "action": a, "soc_end": soc_end})

    plan_q = [[series[i][0].isoformat(), ACTIONS[acts[i]], round(100 * plan["soc"][i] / cap, 1),
               round(buy[i], 4)] for i in range(len(series))]

    return {
        "action": ACTIONS[a0],
        "reason": reason,
        "soc_now": round(inp.soc_pct, 1),
        "expected_soc_end_of_quarter": round(100 * plan["soc"][0] / cap, 1),
        "ceiling_pct": round(inp.ceiling_pct, 1),
        "reserve_pct": reserve_pct,
        "strategy": cfg["strategy"],
        "aggressiveness": cfg["level"],
        "sell_threshold_eur_kwh": cfg["threshold"],
        "hold_allowed": cfg["hold"],
        "cycle_limit": cfg["cycle_limit"],
        "cycles_today": round(inp.discharged_today_kwh / cap, 2),
        "cycles_planned_today": round((inp.discharged_today_kwh + plan["ontladen_dag"][0]) / cap, 2),
        "regime": inp.regime,
        "energy_tax": inp.energy_tax,
        "wear_eur_kwh": inp.wear,
        "price_now": round(buy[0], 4),
        "sell_price_now": round(sell[0], 4),
        "horizon_until": (series[-1][0] + timedelta(minutes=15)).isoformat(),
        "tomorrow_known": inp.tomorrow_known,
        "expected_cost_horizon": round(plan["kosten"], 2),
        "dp_runs": plan["dp_runs"],
        "plan": blocks[:24],
        "plan_quarters": plan_q,
        "next": next_moments(plan_q),
        **inp.extra,
    }


def next_moments(plan_q: list) -> dict:
    """Per actie het eerstvolgende aaneengesloten blok: (start, eind, soc-doel)."""
    out = {}
    for action in ("charge", "discharge", "hold"):
        start = end = target = None
        for st, a, soc, _p in plan_q:
            if start is None:
                if a == action:
                    start = end = st
                    target = soc
            elif a == action:
                end = st
                target = soc
            else:
                break
        if start is not None:
            end = (datetime.fromisoformat(end) + timedelta(minutes=15)).isoformat()
        out[action] = {"start": start, "end": end, "soc_target": target}
    return out


def moment_text(start: str | None, end: str | None, target, now: datetime) -> str:
    """Leesbare tekst voor een gepland blok, zoals de pyscript-versie."""
    if not start:
        return "not planned"
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    soc = "" if target is None else f" · {round(target)}%"
    if s <= now:
        return f"now until {e:%H:%M}{soc}"
    days = (s.date() - now.date()).days
    prefix = "" if days == 0 else ("tomorrow " if days == 1 else f"{s:%d-%m} ")
    return f"{prefix}{s:%H:%M}–{e:%H:%M}{soc}"


def parse_nordpool_raw(raw: list | None, tz) -> list[tuple[datetime, float]]:
    """raw_today/raw_tomorrow van de HACS Nord Pool-sensor -> (start, waarde) per kwartier.

    Uurprijzen worden in vier kwartieren gesplitst.
    """
    out = []
    for item in raw or []:
        try:
            st, en, v = item["start"], item["end"], item["value"]
        except (KeyError, TypeError):
            continue
        if v is None:
            continue
        if isinstance(st, str):
            st = datetime.fromisoformat(st)
        if isinstance(en, str):
            en = datetime.fromisoformat(en)
        if st.tzinfo is None:
            st = st.replace(tzinfo=tz)
            en = en.replace(tzinfo=tz)
        n = max(1, int(round((en - st).total_seconds() / 900.0)))
        for k in range(n):
            out.append((st + timedelta(minutes=15 * k), float(v)))
    return out


def to_all_in(spot: float, energy_tax: float, fee_in: float, vat: float) -> float:
    """Kale beursprijs (EUR/kWh) -> all-in inkoopprijs."""
    return (spot + fee_in + energy_tax) * vat


def flat_profile(yearly_kwh: float) -> list[float]:
    """Vlak profiel als terugval zonder statistieken: kWh per kwartier per uur."""
    return [yearly_kwh / 8760.0 / 4.0] * 24
