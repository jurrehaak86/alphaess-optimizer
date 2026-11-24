# Controlling the battery

The integration only advises. [`automations/battery-control.yaml`](../automations/battery-control.yaml)
is an automation that carries out that advice through the dispatch entities of AlphaESS
Modbus TCP. It's the automation that has controlled the author's SMILE-G3-T10 since the end
of October 2026, switched to this integration's sensors and with personal helpers taken out.

You install it yourself, so you stay in control of what the inverter does.

## What it does

Every quarter hour (at :00:10, :15:10, :30:10 and :45:10) and whenever the advice changes,
it sets the inverter to the mode that matches the advice:

| Advice | Dispatch mode | Dispatch power | Effect |
|---|---|---|---|
| charge | Optimise Consumption (6) | -10 | charges from the grid at full power |
| discharge | Maximise Output (4) | 10 | discharges to the house and the grid |
| hold | Battery only Charges from PV (1) | -10 | doesn't discharge; solar surplus may still charge it |
| balance | Load Following (3) | -10 | the battery supplies the house |

It also has a few safety checks:

- It stops charging once the state of charge reaches the planned level for that quarter,
  or the charge ceiling. The battery then holds.
- It stops discharging at the planned level or at the reserve. The battery then balances.
- If the advice is more than 20 minutes old, or the optimizer is unavailable, the battery
  goes to balance and you get a notification.
- If the state of charge is missing (for example during a backup or a restart), the
  battery goes to balance. After 10 minutes without a state of charge you get a
  notification.
- When the battery is nearly full (above 98 %) and the sun gives more than the house uses,
  it turns on excess export so the surplus goes to the grid. Below 95 %, or when the
  surplus is gone, it turns excess export off again.

## Before you add it

1. **Turn off whatever controls your battery now.** Two automations writing to the
   dispatch entities will fight each other. Also check that no schedule in the AlphaESS app
   overrides dispatch.
2. **Check the dispatch power.** The values -10 and 10 are in kW and fit a 10 kW inverter
   such as the SMILE-G3-T10. Use your own inverter's power: the value of
   `select.alphaess_inverter_inverter_ac_limit`, and the same number you filled in as
   *Max charge/discharge power* during setup. Change every `-10` and `10` under
   `number.alphaess_inverter_dispatch_power`.
3. **Check the entity IDs.** The YAML assumes the default device name *AlphaESS Inverter*,
   which gives `sensor.alphaess_inverter_…` for AlphaESS Modbus TCP and
   `sensor.optimizer_alphaess_inverter_…` for this integration. Renamed your inverter? Use
   find and replace.

## Add it

1. Go to **Settings → Automations & scenes → Create automation → Create new automation**.
2. Open the menu (⋮) and choose **Edit in YAML**.
3. Replace everything with the contents of `battery-control.yaml` and save.

Watch the first few quarters. The *Dispatch mode* entity of AlphaESS Modbus TCP should
follow the *Action* sensor of the optimizer, and the automation's traces (⋮ → Traces) show
which branch ran and why.

## Turning it off

Turn the automation off. The last dispatch command runs out after 15 minutes
(`dispatch_duration`), and the inverter then goes back to its own settings.

## Charging an electric car

The author's own version has one more branch: while the car charges, the battery goes to
*State of Charge Control (2)* with power 0, so it doesn't empty itself into the car. That
branch depends on the charger, so it isn't in the example. If you want it, add a branch
like this as the third option, after *Charge*, with your charger's status entity:

```yaml
      - alias: EV charging
        conditions:
          - condition: state
            entity_id: sensor.your_charger_status
            state: Charging
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.alphaess_inverter_excess_export
          - action: number.set_value
            target:
              entity_id: number.alphaess_inverter_dispatch_power
            data:
              value: 0
          - action: number.set_value
            target:
              entity_id: number.alphaess_inverter_dispatch_duration
            data:
              value: 15
          - action: select.select_option
            target:
              entity_id: select.alphaess_inverter_dispatch_mode
            data:
              option: State of Charge Control (2)
          - action: switch.turn_on
            target:
              entity_id: switch.alphaess_inverter_dispatch
```

Add a state trigger on the same entity, so the battery reacts as soon as the car starts or
stops charging.
