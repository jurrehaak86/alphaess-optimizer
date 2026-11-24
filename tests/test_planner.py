"""Planner zonder Home Assistant: prijzen in, plan uit. Draait met pytest of los."""
import importlib
import pathlib
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "alphaess_optimizer"

# Laad planner/optimizer/const zonder __init__.py (die importeert Home Assistant).
pkg = types.ModuleType("aopt")
pkg.__path__ = [str(PKG)]
sys.modules["aopt"] = pkg
planner = importlib.import_module("aopt.planner")

TZ = timezone(timedelta(hours=1))


def _raw(day: datetime, base: float):
    """Uurprijzen in Nord Pool-formaat: goedkoop 's nachts en midden op de dag, duur 's avonds."""
    out = []
    for h in range(24):
        st = day.replace(hour=h)
        v = base + (0.15 if 17 <= h <= 20 else 0.0) - (0.08 if 11 <= h <= 14 else 0.0)
        out.append({"start": st.isoformat(), "end": (st + timedelta(hours=1)).isoformat(),
                    "value": round(v, 4)})
    return out


def _input(**kw):
    day = datetime(2026, 11, 24, tzinfo=TZ)
    prices = planner.parse_nordpool_raw(_raw(day, 0.25) + _raw(day + timedelta(days=1), 0.26), TZ)
    base = dict(
        now=day.replace(hour=9, minute=7), prices=prices, soc_pct=30.0, capacity_kwh=18.6,
        ceiling_pct=98.0, floor_pct=4.4, power_kw=10.0, eta=0.95,
        load_weekday=planner.flat_profile(3500), load_weekend=planner.flat_profile(3500),
        discharged_today_kwh=0.0, regime="2026", energy_tax=0.0916, vat=1.21, fee_in=0.018,
        fee_out=0.018, netting_deduction=0.0248, wear=0.03, aggressiveness=5,
        backup_target_pct=40.0, backup_weight=1.0, tomorrow_known=True)
    base.update(kw)
    return planner.PlanInput(**base)


def test_uurprijzen_worden_kwartieren():
    day = datetime(2026, 11, 24, tzinfo=TZ)
    assert len(planner.parse_nordpool_raw(_raw(day, 0.2), TZ)) == 96


def test_plan_begint_bij_huidig_kwartier_en_dekt_horizon():
    r = planner.make_plan(_input())
    assert r["action"] in ("charge", "discharge", "balance", "hold")
    assert r["plan_quarters"][0][0].startswith("2026-11-24T09:00")
    assert r["horizon_until"].startswith("2026-11-26T00:00")
    assert len(r["plan_quarters"]) == 4 * (15 + 24)


def test_laadt_in_goedkoop_middagblok_en_ontlaadt_s_avonds():
    r = planner.make_plan(_input())
    acties = {q[0][11:16]: q[1] for q in r["plan_quarters"][:60]}
    assert any(acties[f"{h:02d}:{m:02d}"] == "charge" for h in range(11, 15) for m in (0, 15, 30, 45))
    assert all(acties[f"{h:02d}:00"] != "charge" for h in range(17, 21))


def test_geen_prijzen_geeft_balans():
    assert planner.make_plan(_input(prices=[]))["action"] == "balance"


def test_moment_tekst():
    nu = datetime(2026, 11, 24, 9, 7, tzinfo=TZ)
    assert planner.moment_text(None, None, None, nu) == "not planned"
    s = datetime(2026, 11, 25, 6, 0, tzinfo=TZ).isoformat()
    e = datetime(2026, 11, 25, 6, 30, tzinfo=TZ).isoformat()
    assert planner.moment_text(s, e, 55.2, nu) == "tomorrow 06:00–06:30 · 55%"


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
