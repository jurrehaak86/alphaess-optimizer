"""The example automation in automations/battery-control.yaml, loaded into a test instance of
Home Assistant: it must validate, and pick the right dispatch mode per situation."""
from datetime import timedelta
import pathlib

import pytest
import yaml
from pytest_homeassistant.common import async_mock_service

from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

YAML = pathlib.Path(__file__).resolve().parents[1] / "automations" / "battery-control.yaml"
ACTION = "sensor.optimizer_alphaess_inverter_action"
SOC = "sensor.alphaess_inverter_battery_state_of_charge"
AUTOMATION = "automation.alphaess_battery_optimizer_control"


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The time_pattern trigger keeps its quarter-hour timer after the test."""
    return True


@pytest.fixture
async def calls(hass):
    """Mock the actions the automation calls on the inverter."""
    return {
        "mode": async_mock_service(hass, "select", "select_option"),
        "number": async_mock_service(hass, "number", "set_value"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
        "note": async_mock_service(hass, "persistent_notification", "create"),
    }


async def _setup(hass, *, advice, soc, target, reserve=40, ceiling=95, excess_power=0,
                 excess="off"):
    hass.states.async_set(ACTION, advice, {"expected_soc_end_of_quarter": target})
    hass.states.async_set(SOC, str(soc))
    hass.states.async_set("sensor.optimizer_alphaess_inverter_reserve", str(reserve))
    hass.states.async_set("sensor.optimizer_alphaess_inverter_charge_ceiling", str(ceiling))
    hass.states.async_set("sensor.alphaess_inverter_excess_power", str(excess_power))
    hass.states.async_set("switch.alphaess_inverter_excess_export", excess)
    cfg = yaml.safe_load(YAML.read_text())
    assert await async_setup_component(hass, "automation", {"automation": [cfg]})
    await hass.async_block_till_done()
    assert hass.states.get(AUTOMATION).state == "on", "automation did not validate"


async def _run(hass):
    await hass.services.async_call("automation", "trigger",
                                   {"entity_id": AUTOMATION, "skip_condition": True},
                                   blocking=True)
    await hass.async_block_till_done()


def _mode(calls):
    return calls["mode"][-1].data["option"] if calls["mode"] else None


def _power(calls):
    return [c.data["value"] for c in calls["number"]
            if c.data["entity_id"] == ["number.alphaess_inverter_dispatch_power"]
            or c.data["entity_id"] == "number.alphaess_inverter_dispatch_power"]


async def test_charge(hass, calls):
    await _setup(hass, advice="charge", soc=30, target=43)
    await _run(hass)
    assert _mode(calls) == "Optimise Consumption (6)"
    assert _power(calls)[-1] == -10


async def test_charge_at_target_holds(hass, calls):
    # SoC already at the quarter's target: stop charging, keep the charge
    await _setup(hass, advice="charge", soc=43, target=43)
    await _run(hass)
    assert _mode(calls) == "Battery only Charges from PV (1)"


async def test_discharge(hass, calls):
    await _setup(hass, advice="discharge", soc=80, target=66, reserve=40)
    await _run(hass)
    assert _mode(calls) == "Maximise Output (4)"
    assert _power(calls)[-1] == 10


async def test_discharge_below_reserve_balances(hass, calls):
    await _setup(hass, advice="discharge", soc=39, target=30, reserve=40)
    await _run(hass)
    assert _mode(calls) == "Load Following (3)"


async def test_hold(hass, calls):
    await _setup(hass, advice="hold", soc=50, target=50)
    await _run(hass)
    assert _mode(calls) == "Battery only Charges from PV (1)"


async def test_balance(hass, calls):
    await _setup(hass, advice="balance", soc=50, target=48)
    await _run(hass)
    assert _mode(calls) == "Load Following (3)"


def _is(call, entity_id):
    return call.data["entity_id"] in (entity_id, [entity_id])


async def test_excess_export_when_full_and_sunny(hass, calls):
    await _setup(hass, advice="balance", soc=99, target=99, excess_power=2700)
    await _run(hass)
    assert any(_is(c, "switch.alphaess_inverter_excess_export") for c in calls["on"])
    # auto-off safety net armed (AlphaESS Modbus TCP v1.16.0+)
    assert [c.data["value"] for c in calls["number"]
            if _is(c, "number.alphaess_inverter_excess_export_duration")] == [20]
    assert not calls["mode"]


async def test_excess_export_stops_without_surplus(hass, calls):
    # Full battery, excess export on, but the sun no longer covers the house
    await _setup(hass, advice="balance", soc=97, target=97, excess_power=0, excess="on")
    await _run(hass)
    assert any(_is(c, "switch.alphaess_inverter_excess_export") for c in calls["off"])
    assert _mode(calls) == "Load Following (3)"


async def test_excess_export_hysteresis_keeps_running(hass, calls):
    # Between 95 and 98 % with excess export already on: keep exporting
    await _setup(hass, advice="hold", soc=96, target=96, excess_power=1500, excess="on")
    await _run(hass)
    assert any(_is(c, "switch.alphaess_inverter_excess_export") for c in calls["on"])
    assert not calls["mode"]


async def test_stale_advice_balances_and_notifies(hass, calls, freezer):
    await _setup(hass, advice="charge", soc=30, target=43)
    freezer.tick(timedelta(minutes=25))
    await _run(hass)
    assert _mode(calls) == "Load Following (3)"
    assert calls["note"]


async def test_missing_soc_balances(hass, calls):
    await _setup(hass, advice="discharge", soc="unavailable", target=30)
    await _run(hass)
    assert _mode(calls) == "Load Following (3)"
