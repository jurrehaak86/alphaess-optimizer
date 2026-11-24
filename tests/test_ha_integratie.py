"""Config flow en setup tegen een echte (test)instantie van Home Assistant."""
from datetime import timedelta

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.alphaess_optimizer.const import DOMAIN

AE = "01TESTALPHAESS"


@pytest.fixture(autouse=True)
def _recorder(recorder_mock):
    """Recorder before hass: the integration depends on it."""
    yield


def _raw(day):
    out = []
    for h in range(24):
        st = day + timedelta(hours=h)
        v = 0.25 + (0.15 if 17 <= h <= 20 else 0.0) - (0.08 if 11 <= h <= 14 else 0.0)
        out.append({"start": st, "end": st + timedelta(hours=1), "value": v})
    return out


async def _omgeving(hass):
    ae = MockConfigEntry(domain="alphaess_modbus", entry_id=AE, title="AlphaESS")
    ae.add_to_hass(hass)
    np_ = MockConfigEntry(domain="nordpool", title="Nord Pool")
    np_.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=AE, identifiers={("alphaess_modbus", "inv1")}, name="AlphaESS Inverter")
    reg = er.async_get(hass)
    for key, sfx, val, attrs in (
        ("battery_state_of_charge", "soc_battery", "35", {"unit_of_measurement": "%"}),
        ("battery_capacity", "battery_capacity_kwh", "18.6", {"unit_of_measurement": "kWh"}),
        ("current_house_load", "current_house_load", "300",
         {"unit_of_measurement": "W", "device_class": "power", "state_class": "measurement"}),
    ):
        e = reg.async_get_or_create("sensor", "alphaess_modbus", f"{AE}_{sfx}",
                                    suggested_object_id=f"alphaess_inverter_{key}",
                                    config_entry=ae, device_id=dev.id)
        hass.states.async_set(e.entity_id, val, attrs)
    p = reg.async_get_or_create("sensor", "nordpool", "np_nl", suggested_object_id="nordpool_nl",
                                config_entry=np_)
    today = dt_util.start_of_local_day()
    hass.states.async_set(p.entity_id, "0.30", {
        "raw_today": _raw(today), "raw_tomorrow": _raw(today + timedelta(days=1)),
        "tomorrow_valid": True, "price_in_cents": False})
    return dev, p.entity_id


async def test_flow_en_setup(recorder_mock, hass):
    dev, price = await _omgeving(hass)

    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        "device_id": dev.id, "power_kw": 10, "floor_pct": 4.4, "max_soc_pct": 98, "eta": 0.95})
    assert r["step_id"] == "prices", r.get("errors")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        "price_entity": price, "price_all_in": True, "fee_in": 0.018, "fee_out": 0.018,
        "netting_deduction": 0.0248, "vat_pct": 21})
    assert r["step_id"] == "solar", r.get("errors")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["step_id"] == "usage"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        "holiday_factor": 0.45, "yearly_kwh": 3500})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Optimizer AlphaESS Inverter"
    assert r["data"]["soc_entity"] == "sensor.alphaess_inverter_battery_state_of_charge"
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is config_entries.ConfigEntryState.LOADED
    ents = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    ids = {e.translation_key: e.entity_id for e in ents}
    actie = hass.states.get(ids["action"])
    assert actie.state in ("charge", "discharge", "balance", "hold"), actie
    assert actie.attributes["profile"] == "flat (not enough statistics)"
    assert len(actie.attributes["plan_quarters"]) > 24
    assert hass.states.get(ids["aggressiveness"]).state == "5"

    # instelling wijzigen -> nieuw plan met dat niveau
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": ids["aggressiveness"], "value": 9}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(ids["action"]).attributes["aggressiveness"] == 9
    # zonder BMS-sensor (AlphaESS Modbus TCP < v1.16.0) plant laden met het volle vermogen
    assert hass.states.get(ids["action"]).attributes["charge_power_kw"] == 10.0
    assert hass.states.get(ids["action"]).attributes["bms_charge_power_w"] is None

    # BMS-laadlimiet verschijnt na een update van AlphaESS Modbus TCP: wordt zonder nieuwe
    # setup gevonden en begrenst het laadvermogen (3880 W DC / ETA 0,95 = 4,08 kW AC)
    ae = hass.config_entries.async_get_entry(AE)
    bms = er.async_get(hass).async_get_or_create(
        "sensor", "alphaess_modbus", f"{AE}_battery_max_charge_power",
        suggested_object_id="alphaess_inverter_battery_max_charge_power",
        config_entry=ae, device_id=dev.id)
    hass.states.async_set(bms.entity_id, "3880", {"unit_of_measurement": "W"})
    await entry.runtime_data.async_refresh()   # zoals de kwartiertrigger
    await hass.async_block_till_done()
    attrs = hass.states.get(ids["action"]).attributes
    assert attrs["charge_power_kw"] == 4.08 and attrs["bms_charge_power_w"] == 3880
    stappen = [b[2] - a[2] for a, b in zip(attrs["plan_quarters"], attrs["plan_quarters"][1:])
               if b[1] == "charge"]
    assert not stappen or max(stappen) <= 4.08 / 4 * 0.95 / 18.6 * 100 + 0.2

    # tweede keer dezelfde omvormer -> afbreken
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        "device_id": dev.id, "power_kw": 10, "floor_pct": 4.4, "max_soc_pct": 98, "eta": 0.95})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"

    # options flow doorlopen
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "power_kw": 5, "floor_pct": 10, "max_soc_pct": 95, "eta": 0.95})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "price_entity": price, "price_all_in": True, "fee_in": 0.018, "fee_out": 0.018,
        "netting_deduction": 0.0248, "vat_pct": 21})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "holiday_factor": 0.5, "yearly_kwh": 3000})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_zonder_alphaess_afbreken(recorder_mock, hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "alphaess_missing"
