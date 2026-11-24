"""Controle: de rekenkern in de integratie geeft exact hetzelfde plan als de live
pyscript-versie. Draai vanuit de repo-root:

    python3 tests/test_kern_gelijk.py [pad/naar/accu_optimizer.py]

Zonder pad wordt de kopie in het Homelab-project gebruikt.
"""
import importlib.util
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIG = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT.parent / "home-assistant" / "accu-optimizer" / "accu_optimizer.py")


def laad_origineel(pad):
    ns = {
        "pyscript_compile": lambda f: f,
        "time_trigger": lambda *a, **k: (lambda f: f),
        "service": lambda f: f,
        "__name__": "accu_optimizer_orig",
    }
    exec(compile(pad.read_text(), str(pad), "exec"), ns)
    return ns


def laad_nieuw():
    pad = ROOT / "custom_components" / "alphaess_optimizer" / "optimizer.py"
    spec = importlib.util.spec_from_file_location("kern", pad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario(rnd):
    n = rnd.choice([40, 64, 96, 140])
    cap = 18.6
    basis = rnd.uniform(0.15, 0.30)
    buy = [round(basis + 0.12 * rnd.random() + (0.10 if 68 <= (t % 96) <= 84 else 0.0), 4)
           for t in range(n)]
    sell = [b - 0.0248 for b in buy]
    load = [round(rnd.uniform(0.03, 0.30), 3) for _ in range(n)]
    split = rnd.randint(1, n - 1)
    dag = [0 if t < split else 1 for t in range(n)]
    floor = 0.044 * cap
    soc = rnd.uniform(floor, 0.95 * cap)
    plafond = rnd.uniform(0.6, 0.98) * cap
    return dict(buy=buy, sell=sell, load=load, dag=dag, soc=soc, floor=floor,
                plafond=plafond, cap=cap, used=rnd.uniform(0, 8),
                reserve=rnd.uniform(floor, 0.6 * cap))


def main():
    oud = laad_origineel(ORIG)
    nieuw = laad_nieuw()
    rnd = random.Random(42)
    fouten = 0
    for i in range(30):
        s = scenario(rnd)
        limit = rnd.choice([None, 1.5 * s["cap"], 1.0 * s["cap"]])
        tv = 0.95 * nieuw.kwantiel(s["buy"], 0.25)
        args_e = (s["buy"], s["sell"], s["load"], s["dag"], s["soc"], s["floor"], s["plafond"],
                  s["used"], limit, 2.5, 0.95, 0.25, 1.2, tv, True, 1e-5, True, True, 0.03, 0.05,
                  None, 0.4 * s["cap"], 0.0005, True, True, None, 0.5, True)
        args_p = (s["buy"], s["sell"], s["load"], s["dag"], s["soc"], s["floor"], s["plafond"],
                  s["reserve"], s["used"], limit, 2.5, 0.95, 0.25, 1.2, tv, True, 1e-5, True,
                  None, True, 0.03, 0.0, None, None, 0.4 * s["cap"], 0.0005)
        args_i = (s["buy"], s["sell"], s["load"], s["dag"], s["soc"], s["floor"], s["plafond"],
                  s["used"], limit, 2.5, 0.95, 0.25, 1.2, tv, True, 1e-5, True, True, 0.03, 0.02,
                  0.4 * s["cap"], 0.0005)
        for naam, args in (("accu_plan_eigen", args_e), ("accu_plan", args_p),
                           ("accu_plan_intern", args_i)):
            a = oud[naam](*args)
            b = getattr(nieuw, naam)(*args)
            if a != b:
                fouten += 1
                print(f"VERSCHIL scenario {i} {naam}")
        for regime in ("2026", "2027"):
            for p in s["buy"][:5]:
                x = oud["verkoopprijs"](p, regime, 0.0916, 1.21, 0.018, 0.018)
                y = nieuw.verkoopprijs(p, regime, 0.0916, 1.21, 0.018, 0.018, 0.0248)
                if abs(x - y) > 1e-12:
                    fouten += 1
                    print(f"VERSCHIL verkoopprijs {regime} {p}")
    print("OK: identiek" if fouten == 0 else f"{fouten} verschillen")
    sys.exit(1 if fouten else 0)


if __name__ == "__main__":
    main()
