# AlphaESS Battery Optimizer

I built this optimizer to run several strategies at once on an AlphaESS home battery. It
reads the battery through the [AlphaESS Modbus TCP integration](https://github.com/senalse/ha-alphaess-modbus)
by senalse, which does the hard work of talking to the inverter. Many thanks for that.

Your own home comes first: buy electricity when it's cheap, store solar energy, and use
what's stored in the house. Where it pays off, the optimizer sells the surplus to the grid.
You decide how far it goes with settings for aggressiveness, backup power and more.

Feedback is always welcome: open an [issue](https://github.com/jurrehaak86/alphaess-optimizer/issues).

## What it does

Home Assistant integration that plans your AlphaESS home battery per quarter hour on
dynamic (Nord Pool) prices: **charge**, **discharge**, **balance** (battery supplies the
house) or **hold**. It uses dynamic programming over the state of charge across all
known prices (today, and tomorrow once published) and replans every 15 minutes.

> **Status: v0.1, advice only.** The integration does not control the inverter yet. It
> publishes a sensor with the decision and the full plan, which you can follow in an
> automation of your own. Not affiliated with AlphaESS.

Netting rules and energy tax are Dutch (saldering until 2026, none from 2027).

![Battery plan chart](docs/images/plan-chart.png)

## Requirements

| | |
|---|---|
| [AlphaESS Modbus TCP](https://github.com/senalse/ha-alphaess-modbus) | Required. State of charge, capacity and house load come from here. Should work with every model that integration supports; tested on a SMILE-G3-T10 |
| [Nord Pool, community version](https://github.com/custom-components/nordpool) | Required. Needs the `raw_today` / `raw_tomorrow` attributes. The built-in Nord Pool integration is not supported yet |
| Recorder | Built in. The consumption profile comes from long-term statistics |
| Solar forecast | Optional. Any sensor with "remaining today" in kWh (Forecast.Solar, Solcast, ...) |

## Installation

The full guide, with every setup field explained, is in [docs/installation.md](docs/installation.md).

1. Home Assistant 2026.11 and later: Settings → Marketplace → Add from link, and paste this repository's URL.
   On 2026.10 and older: HACS → ⋮ → Custom repositories → add it as *Integration*.
2. Install **AlphaESS Battery Optimizer** and restart Home Assistant.
3. Settings → Devices & services → Add integration → **AlphaESS Battery Optimizer**.

## Setup

1. **Battery**: pick your AlphaESS inverter. Max power, minimum and maximum SoC, efficiency.
2. **Prices**: the Nord Pool sensor. Tick *all-in* if your sensor already includes energy
   tax, fees and VAT (via `additional_costs`); otherwise the integration adds them.
3. **Solar** (optional): forecast of remaining production today. The charge ceiling keeps
   room for it.
4. **Consumption**: optional EV charging power (subtracted from the profile), holiday
   switch and factor, yearly consumption as fallback.

Everything except the inverter can be changed later under *Configure*.

## Entities

| Entity | |
|---|---|
| `sensor.…_action` | `charge` / `discharge` / `balance` / `hold`. Attributes: reason, plan in blocks, `plan_quarters` (start, action, SoC, price), reserve, cycles, cost |
| `sensor.…_next_charge` / `_next_discharge` / `_next_hold` | Next block as text, e.g. `tomorrow 06:00–06:30 · 55%` |
| `sensor.…_reserve`, `sensor.…_charge_ceiling` | Diagnostics |
| `number.…_aggressiveness` | 1 = only own consumption, 5 = default, 10 = free trading |
| `number.…_backup_target`, `…_backup_weight` | Soft lower bound for backup |
| `number.…_energy_tax`, `…_wear_cost` | EUR/kWh. Update the energy tax every 1 January |
| `select.…_netting_regime` | `2026` (netting) or `2027` (no netting) |

## How it decides

- **Own consumption first** (levels 1–7): first a plan without selling, then selling only
  what is above the reserve (consumption until the next charging moment). Never buys to
  sell, never holds at the expense of own use.
- **Optimal** (levels 8–10): free optimisation.
- Remaining charge at the end of the horizon is valued at ETA × a price quantile, so the
  battery is not drained at the horizon edge.
- A daily cycle limit is enforced with a Lagrange penalty on discharged kWh.
- Wear cost per discharged kWh is part of every trade-off.

## Not (yet) in v0.1

- Controlling the inverter (dispatch). Planned for v0.2.
- Solar production per quarter inside the model; solar only lowers the charge ceiling.
- Holiday days are not excluded from the statistics.
- Built-in Nord Pool integration and other price sources.

## Dashboard

An example view with the plan chart, live values and the optimizer settings is in
[dashboard/battery-view.yaml](dashboard/battery-view.yaml). See [docs/dashboard.md](docs/dashboard.md).

## Development

`tests/test_kern_gelijk.py` checks that the planning core is identical to the pyscript
version that runs the author's own battery. That reference file isn't in this repository,
so the check only runs where it is available:

```bash
python3 tests/test_kern_gelijk.py path/to/accu_optimizer.py
```

The Home Assistant tests use `pytest-homeassistant`, which Home Assistant publishes with
every release and which pins that same version. It needs Python 3.14 or newer. Bump the
pin in `requirements_test.txt` together with the Home Assistant you run.

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```

## About this project

I developed this with Claude, which also wrote the scripts. The battery control has been
tested for several months on my own setup and works as intended. The planning core in this
integration is the same code that plans my battery today; packaging it as an integration
(v0.1) is new.

Feedback is always welcome: open an [issue](https://github.com/jurrehaak86/alphaess-optimizer/issues).
