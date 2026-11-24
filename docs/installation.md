# Installation and setup guide

This guide walks through installing AlphaESS Battery Optimizer for Home Assistant and
explains every field in the setup screens: what it means, where to find the value, and
what to fill in. The help text in Home Assistant itself is short; this is the long version.

The integration gives advice. It tells you per quarter hour whether the battery should
charge, discharge, balance or hold, and publishes the full plan as sensors. It does not
send commands to the inverter, so you can safely run it next to whatever controls your
battery today. To act on the advice, add the example automation described in
[automation.md](automation.md).

The price and tax logic is Dutch: netting (saldering) until the end of 2026, no netting
from 1 January 2027.

Examples in this guide come from the author's SMILE-G3-T10 with an 18.6 kWh battery. Entity
IDs assume the default device name *AlphaESS Inverter*.

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

### AlphaESS inverter

The inverter as a device from AlphaESS Modbus TCP, usually called *AlphaESS Inverter*. The
integration finds three sensors on it by itself: state of charge, battery capacity and
current house load. Pick the inverter, not the battery or another device.

If you get "State of charge, capacity or house load not found on this device", one of
those three sensors is disabled. Enable it under the AlphaESS device and try again.

### Max charge/discharge power

The highest power, in kW, at which the battery charges from the grid or discharges to the
house and grid. The optimizer uses it to work out how much energy fits in one quarter
hour: 10 kW is at most 2.5 kWh per quarter.

Where to find it: AlphaESS Modbus TCP shows the inverter's limit as
`select.alphaess_inverter_inverter_ac_limit`. You can also look it up on your model's
datasheet. If you've set a lower limit on purpose, fill in that lower value.

What happens if it's wrong: too high and the plan counts on more energy per quarter than
the battery can move, so it plans too few charging quarters. Too low and it leaves cheap
quarters unused.

Default 10 kW. Example: 10 kW on a SMILE-G3-T10.

### Minimum state of charge (inverter floor)

The state of charge at which the inverter stops discharging, in percent. The optimizer
never plans below it. Charge below this level counts as unusable.

Where to find it: `number.alphaess_inverter_discharging_cutoff_soc`. Fill in the same
value or a little higher.

Default 4.4 %. Example: the inverter cut-off is 4 %.

### Maximum state of charge

The highest state of charge the optimizer charges to from the grid, in percent. Solar can
still fill the battery further, as far as the inverter allows.

Where to find it: the inverter also has a limit of its own,
`number.alphaess_inverter_charging_cutoff_soc`. Fill in that value or lower. A higher value
makes the plan count on charge the inverter won't accept.

Default 98 %. Example: the inverter stops charging at 96 %, so 96 is the right value.

### Efficiency per direction

The share of the energy that survives one direction, charging or discharging. 0.95 means
5 % is lost on the way in and 5 % on the way out, about 90 % round trip. The optimizer
only charges from the grid when the price difference covers these losses.

Leave it at 0.95 unless you've measured your own losses at the AC side. The battery's own
charge and discharge counters don't include the inverter's losses, so they make the
efficiency look better than it is.

## Step 2: Prices

### How the optimizer uses prices

The purchase price per quarter hour comes from the Nord Pool sensor. The feed-in price is
derived from it:

- Netting regime 2026: feed-in price = purchase price minus the netting deduction.
- Netting regime 2027: feed-in price = bare exchange price minus the feed-in fee.

You choose the regime later with the *Netting regime* entity; the default is 2026.

### Nord Pool price sensor

The price sensor from the community Nord Pool integration, for example
`sensor.nordpool_kwh_nl_eur_3_10_0`. Its name depends on the region, currency and options
you chose in Nord Pool. The optimizer reads the `raw_today` and `raw_tomorrow`
attributes, so it has to be this integration and not the built-in Nord Pool integration.

If you get "This sensor has no raw_today attribute", you picked a sensor from another
integration.

### Price already includes tax, fees and VAT

On if the sensor shows what you actually pay per kWh: exchange price plus your supplier's
purchase fee, plus energy tax, plus VAT. That's the case when you filled in
`additional_costs` and VAT in the Nord Pool setup. Off if the sensor shows the bare
exchange price; the optimizer then adds the purchase fee, energy tax and VAT itself.

How to check: open the Nord Pool sensor under **Developer tools → States** and compare its
value with the current price in your supplier's app. Within a cent means on.

Default on.

### Supplier purchase fee (excl. VAT)

The fixed amount your supplier adds to every kWh you buy, in euro excluding VAT. Dutch
suppliers call it *inkoopvergoeding* or *opslag*. You find it on your supplier's rate card
or in the contract.

It's used to strip the price back to the bare exchange price, which the 2027 feed-in price
needs, and to build the all-in price when the sensor isn't all-in. So fill it in correctly
even if your sensor is all-in.

Default €0.018.

### Supplier feed-in fee

The amount your supplier deducts from every kWh you export once netting has ended, in euro
per kWh. Dutch suppliers call it *terugleververgoeding* or *terugleverkosten*. Only used in
netting regime 2027.

Default €0.018.

### Deduction on feed-in price during netting

Under netting (2026), some suppliers pay back the full kWh price for every kWh you export,
minus a fixed amount. Fill in that amount in euro. Only used in netting regime 2026.

Default €0.0248, which is what Tibber NL listed in October 2026. Check your own supplier;
if they pay back the full price, fill in 0.

### VAT

Dutch VAT on electricity: 21 %. Leave it unless the rate changes.

## Step 3: Solar (optional)

### Solar forecast remaining today

A sensor with the expected solar yield for the rest of today, in kWh (Wh works too). Each
forecast integration names it differently:

| Integration | Sensor name |
|---|---|
| Forecast.Solar | *Estimated energy production - remaining today* |
| Solcast | *Forecast Remaining Today* |

The optimizer keeps room in the battery for that energy. The charge ceiling becomes
`100 % − remaining solar ÷ capacity`, never above the maximum state of charge from step 1.
With 3 kWh of sun still to come and an 18.6 kWh battery, it charges from the grid to at
most 84 %. In the evening the remaining solar is zero and the ceiling is back at the
maximum.

Leave it empty if you have no panels or no forecast. The ceiling is then the maximum state
of charge.

## Step 4: Consumption

The optimizer needs to know how much your house uses per hour, so it keeps enough in the
battery until the next cheap moment. It builds that profile itself from the long-term
statistics of *Current House Load* over the last 28 days, with weekdays and weekends
apart. You don't pick that sensor; it comes from the inverter in step 1.

### EV charging power

A power sensor (W or kW) of your car charger. Its usage is subtracted from the house
profile, because the battery shouldn't reserve energy for charging the car.

Fill it in if the charger sits behind the same meter as the house, because AlphaESS then
counts the car as house load. Leave it empty if you have no EV or the charger has its own
connection.

### Holiday switch

An `input_boolean`, `switch` or `binary_sensor` that is on while you're away. While it's
on, the optimizer multiplies the profile by the holiday factor below. If you don't have
one, create a toggle helper under **Settings → Devices & services → Helpers**.

### Consumption factor during holiday

How much of a normal day the house uses while you're away. 0.45 means 45 %: the fridge,
standby devices and heating keep running. The author's house measured 41 %.

Default 0.45.

### Yearly consumption

Your yearly electricity use in kWh, from your energy bill. Only used while there are too
few statistics: the optimizer then assumes a flat profile of yearly use ÷ 8760 per hour.

The profile needs at least three weekday samples and two weekend samples for every hour of
the day. On a fresh Home Assistant that takes about two weeks. Until then the `profile`
attribute of the Action sensor shows `flat (not enough statistics)`.

Default 3000 kWh.

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

## Controlling the battery

Once the advice looks right, add the example automation that carries it out. See
[automation.md](automation.md).

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

The integration only advises, so your battery keeps following whatever controls it. To
compare the two, put the Action sensor and your battery's SoC side by side in a
history graph.

### No AlphaESS logo

Home Assistant caches brand images in the browser. Do a hard
refresh, or open the page in a private window.
