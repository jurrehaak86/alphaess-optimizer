# Installation and setup guide

This guide walks through installing AlphaESS Battery Optimizer and explains every field
in the setup screens: what it means, where to find the value, and what the default is.

Version 0.1 only gives advice. It tells you per quarter hour whether the battery should
charge, discharge, balance or hold, but it does not send commands to the inverter. You
can safely run it next to whatever controls your battery today.

The price and tax logic is Dutch: netting (saldering) until the end of 2026, no netting
from 1 January 2027.

## Before you start

You need three things in Home Assistant:

1. AlphaESS Modbus TCP ([senalse/ha-alphaess-modbus](https://github.com/senalse/ha-alphaess-modbus)),
   set up and connected to your inverter. Check that these sensors have values:
   - Battery State of Charge
   - Battery Capacity
   - Current House Load
2. The community Nord Pool integration ([custom-components/nordpool](https://github.com/custom-components/nordpool)),
   installed from the Marketplace or HACS. The built-in Nord Pool integration does not work
   yet. The community version exposes the
   prices as `raw_today` and `raw_tomorrow` attributes, and that is what the optimizer reads.
3. Recorder with long-term statistics, which every default install has. The
   consumption profile is built from the statistics of your house load.

Optional: a solar forecast integration such as Forecast.Solar or Solcast.

## Install

Home Assistant 2026.11 replaced HACS with the built-in Marketplace. Use the steps for your
version.

On 2026.11 and later:

1. Go to **Settings → Marketplace**. The first time, read and accept the notice about
   community projects.
2. Choose **Add from link** and paste `https://github.com/jurrehaak86/alphaess-optimizer`.
   This needs a GitHub account connected to the Marketplace.
3. Install **AlphaESS Battery Optimizer** and restart Home Assistant.

On 2026.10 and older:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/jurrehaak86/alphaess-optimizer` with type **Integration**.
3. Search for **AlphaESS Battery Optimizer**, install it and restart Home Assistant.

Then go to **Settings → Devices & services → Add integration** and pick
**AlphaESS Battery Optimizer**.

If the integration stops right away with "Install and set up the AlphaESS Modbus TCP
integration first", Home Assistant has no AlphaESS Modbus entry yet. The same goes for
Nord Pool on the second screen.

## Step 1: Battery

| Field | Default | What to fill in |
|---|---|---|
| AlphaESS inverter | none | Your inverter, as a device from AlphaESS Modbus TCP. State of charge, capacity and house load are picked up from this device automatically. |
| Max charge/discharge power | 10 kW | The highest AC power your inverter charges or discharges at. Look it up on the datasheet of your model. Too high makes the plan count on energy the battery can't deliver in one quarter. |
| Minimum state of charge | 4.4 % | The SoC the inverter stops discharging at. Use the cut-off you set on the inverter or in the AlphaESS app. The optimizer never plans below it. |
| Maximum state of charge | 98 % | The highest SoC the optimizer charges to from the grid. Solar can still fill the battery above it. |
| Efficiency per direction | 0.95 | Share of the energy that survives one direction (charge or discharge). 0.95 gives about 90 % round trip. Leave it unless you've measured your own losses. |

You get "State of charge, capacity or house load not found on this device" if you pick a
device that isn't the inverter itself, or if one of those three sensors is disabled.
Enable it under the AlphaESS device and try again.

## Step 2: Prices

| Field | Default | What to fill in |
|---|---|---|
| Nord Pool price sensor | none | The sensor from the community Nord Pool integration, for example `sensor.nordpool_kwh_nl_eur_3_10_0`. The name depends on your Nord Pool settings. |
| Price already includes tax, fees and VAT | on | On if the sensor already shows what you pay per kWh, which is the case when you filled in additional costs and VAT in the Nord Pool setup. Off if the sensor shows the bare exchange price. The optimizer then adds the purchase fee, energy tax and VAT itself. |
| Supplier purchase fee (excl. VAT) | €0.018/kWh | The fixed amount your supplier adds to every kWh you buy, excluding VAT. Your supplier's rate card lists it. Only used when the sensor isn't all-in, and to work out the feed-in price from 2027. |
| Supplier feed-in fee | €0.018/kWh | The amount your supplier deducts from every kWh you export once netting ends (2027). |
| Deduction on feed-in price during netting | €0.0248/kWh | Under netting (2026), some suppliers pay back the full kWh price minus a fixed amount. Fill in that amount. The default is what Tibber NL listed in October 2026. Check your own supplier. |
| VAT | 21 % | Dutch VAT on electricity. |

"This sensor has no raw_today attribute" means you picked a price sensor from another
integration, or one from the built-in Nord Pool integration.

### How to check the all-in price

Open the Nord Pool sensor under **Developer tools → States** and compare its value with
the current price in your supplier's app. If the two are within a cent, leave all-in on.

## Step 3: Solar (optional)

| Field | Default | What to fill in |
|---|---|---|
| Solar forecast remaining today | empty | A sensor with the expected solar yield for the rest of today, in kWh. Forecast.Solar calls it *Estimated energy production - remaining today*, Solcast *Forecast Remaining Today*. |

The forecast lowers the charge ceiling, so the battery has room left for the sun:
`ceiling = 100 % − remaining solar ÷ capacity`, never above the maximum SoC from step 1.
With 3 kWh of sun still to come and an 18.6 kWh battery, the optimizer charges from the
grid to at most 84 %. Leave the field empty if you have no panels or no forecast. The
ceiling is then simply the maximum SoC.

The solar forecast doesn't enter the quarter-hour plan itself yet. On a sunny afternoon
the real SoC can rise faster than the plan expects. The optimizer replans every quarter,
so it catches up.

## Step 4: Consumption

The optimizer needs to know how much your house uses per hour, so it can keep enough in
the battery until the next cheap moment. It builds that profile from the long-term
statistics of *Current House Load* over the last 28 days, with weekdays and weekends
apart.

| Field | Default | What to fill in |
|---|---|---|
| EV charging power | empty | A power sensor (W or kW) of your car charger. Its usage is subtracted from the profile, because the battery shouldn't reserve energy for the car. Leave it empty if you have no EV, or if the charger isn't part of the house load. |
| Holiday switch | empty | An `input_boolean`, `switch` or `binary_sensor` that is on while you're away. |
| Consumption factor during holiday | 0.45 | The profile is multiplied by this while the holiday switch is on. 0.45 means the house uses 45 % of normal. |
| Yearly consumption | 3000 kWh | Only used as a fallback while there are too few statistics: then it assumes a flat profile of yearly usage ÷ 8760 per hour. |

The profile needs at least three weekday samples and two weekend samples for every hour
of the day. On a fresh Home Assistant that takes about two weeks. Until then the
`profile` attribute of the Action sensor shows `flat (not enough statistics)`.

## Changing settings later

Everything except the inverter can be changed under **Settings → Devices & services →
AlphaESS Battery Optimizer → Configure**. The integration reloads after you save.

The following settings are entities, so you can put them on a dashboard or change them
from an automation:

| Entity | Default | Meaning |
|---|---|---|
| Aggressiveness | 5 | 1 to 10. See the table below. |
| Backup target | 40 % | Soft lower limit for backup power. The optimizer tops up to around this level when it's cheap, but may go below it for a real price peak. |
| Backup weight | 1.0 | How much the backup target counts. 0 turns it off. Each unit costs €0.0005 per kWh below the target per quarter hour, about 4.8 cents per kWh per day. The cost only exists in the trade-off; you don't pay it. |
| Energy tax | €0.0916/kWh | Dutch energy tax, first bracket, excluding VAT. 2026 rate. Update it every 1 January. |
| Wear cost | €0.03/kWh | Battery wear per kWh that comes out of the battery. See below. |
| Netting regime | 2026 | Switch to `2027` on 1 January 2027, when netting ends. |

### Aggressiveness

| Level | Strategy | Sells when the margin is at least | Max cycles per day |
|---|---|---|---|
| 1 | own consumption first, never holds | €0.15/kWh | 1.0 |
| 2 | own consumption first, never holds | €0.12/kWh | 1.0 |
| 3 | own consumption first | €0.10/kWh | 1.0 |
| 4 | own consumption first | €0.07/kWh | 1.5 |
| 5 | own consumption first | €0.05/kWh | 1.5 |
| 6 | own consumption first | €0.03/kWh | 1.5 |
| 7 | own consumption first | €0.02/kWh | 1.5 |
| 8 | free optimisation | €0.05/kWh | 1.5 |
| 9 | free optimisation | €0.02/kWh | 2.0 |
| 10 | free optimisation | €0.00/kWh | 2.0 |

*Own consumption first* means the battery covers your house first. It only buys from the
grid for your own later use, and only sells what is above the reserve. *Free
optimisation* may also buy to sell later. The cycle limit includes what the house takes
from the battery.

Lower levels also value the charge left at the end of the price horizon higher, so the
battery is less likely to be emptied in the last hours that have known prices.

### Working out the wear cost

Wear cost = battery price ÷ (warranted cycles × usable kWh per cycle).

Two modules at €1,950 each, rated for 6,000 cycles of 18.6 kWh, comes to
3,900 ÷ (6,000 × 18.6) ≈ €0.035/kWh. Every trade must earn at least this before the
optimizer discharges for it. Set it to 0 to leave wear out.

## What you get

All entities belong to one device, named after your inverter.

| Entity | Example | Content |
|---|---|---|
| Action | `hold` | `charge`, `discharge`, `balance` or `hold` for the current quarter hour. |
| Next charge / Next discharge / Next hold | `tomorrow 11:45–13:15 · 88%` | The next block of that action, with the expected SoC at the end. |
| Reserve | 45 % | What the battery keeps for your own use until the next charging moment. |
| Charge ceiling | 95 % | The highest SoC the plan charges to from the grid right now. |

The four actions:

- `charge`: from the grid at full power, up to the charge ceiling.
- `discharge`: at full power to the house and the grid, down to the reserve.
- `balance`: the battery supplies the house, the normal self-consumption mode.
- `hold`: the battery stays put and the grid supplies the house. This saves stored
  energy for a more expensive moment later.

The Action sensor carries the whole plan in its attributes:

| Attribute | Content |
|---|---|
| `reason` | One line explaining the current choice. |
| `plan` | The plan in blocks: from, to, action, SoC at the end. |
| `plan_quarters` | Every quarter hour: start, action, expected SoC, price. Handy for charts. |
| `reserve_pct`, `ceiling_pct` | The reserve and ceiling the plan used. |
| `cycles_today`, `cycles_planned_today` | Cycles done and planned today. |
| `price_now`, `sell_price_now` | Purchase and feed-in price of this quarter. |
| `profile` | Where the consumption profile came from. |
| `updated`, `calc_time_s` | Time of the last plan and how long it took. |

The plan is recalculated every quarter hour on the hour, and right away when you change
one of the setting entities.

## Dashboard

For a ready-made view with the plan chart, see [dashboard.md](dashboard.md).

## Troubleshooting

### The integration keeps retrying to start

The Action sensor needs a state of charge,
a capacity and at least one price. When the inverter or Nord Pool is unavailable,
for example during a backup or a restart, the integration waits and tries again.

### `profile` stays on `flat`

Check that Current House Load has long-term statistics.
It needs a `state_class` of `measurement`, which AlphaESS Modbus TCP sets. Then give it
time; see step 4.

### The plan doesn't match what my battery does

In v0.1 the integration only advises, so your battery keeps following its own control. To compare, put the Action sensor and your battery's SoC side by side in a
history graph.

### No AlphaESS logo

Home Assistant caches brand images in the browser. Do a hard
refresh, or open the page in a private window.
