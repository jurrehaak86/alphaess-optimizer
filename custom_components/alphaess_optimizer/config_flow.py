"""Config flow: AlphaESS-omvormer kiezen, dan prijzen, zon en verbruik."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import selector as sel

from .const import (
    ALPHAESS_DOMAIN,
    ALPHAESS_SUFFIX,
    CONF_CAPACITY,
    CONF_DEVICE,
    CONF_ETA,
    CONF_EV_POWER,
    CONF_FEE_IN,
    CONF_FEE_OUT,
    CONF_FLOOR_PCT,
    CONF_HOLIDAY,
    CONF_HOLIDAY_FACTOR,
    CONF_HOUSE_LOAD,
    CONF_MAX_SOC,
    CONF_NETTING_DEDUCTION,
    CONF_POWER_KW,
    CONF_PRICE,
    CONF_PRICE_ALL_IN,
    CONF_PV_REMAINING,
    CONF_SOC,
    CONF_VAT_PCT,
    CONF_YEARLY_KWH,
    DEFAULTS,
    DOMAIN,
    NORDPOOL_DOMAIN,
)


def _num(lo: float, hi: float, step: float | str, unit: str | None = None) -> sel.NumberSelector:
    cfg = sel.NumberSelectorConfig(min=lo, max=hi, step=step, mode=sel.NumberSelectorMode.BOX)
    if unit:
        cfg["unit_of_measurement"] = unit
    return sel.NumberSelector(cfg)


def _ent(**kw) -> sel.EntitySelector:
    return sel.EntitySelector(sel.EntitySelectorConfig(**kw))


def find_alphaess_entities(hass: HomeAssistant, device_id: str) -> dict[str, str]:
    """Entities van ha-alphaess-modbus op dit apparaat, via het unique_id-achtervoegsel."""
    reg = er.async_get(hass)
    found: dict[str, str] = {}
    for ent in er.async_entries_for_device(reg, device_id):
        if ent.platform != ALPHAESS_DOMAIN or ent.domain != "sensor":
            continue
        for key, suffix in ALPHAESS_SUFFIX.items():
            if str(ent.unique_id).endswith(suffix):
                found[key] = ent.entity_id
    return found


def _battery_schema(d: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_POWER_KW, default=d.get(CONF_POWER_KW, DEFAULTS[CONF_POWER_KW])):
            _num(0.5, 50, 0.1, "kW"),
        vol.Required(CONF_FLOOR_PCT, default=d.get(CONF_FLOOR_PCT, DEFAULTS[CONF_FLOOR_PCT])):
            _num(0, 50, 0.1, "%"),
        vol.Required(CONF_MAX_SOC, default=d.get(CONF_MAX_SOC, DEFAULTS[CONF_MAX_SOC])):
            _num(50, 100, 1, "%"),
        vol.Required(CONF_ETA, default=d.get(CONF_ETA, DEFAULTS[CONF_ETA])):
            _num(0.8, 1.0, 0.01),
    })


def _price_schema(d: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PRICE, default=d.get(CONF_PRICE, vol.UNDEFINED)):
            _ent(domain="sensor", integration=NORDPOOL_DOMAIN),
        vol.Required(CONF_PRICE_ALL_IN, default=d.get(CONF_PRICE_ALL_IN, DEFAULTS[CONF_PRICE_ALL_IN])):
            sel.BooleanSelector(),
        vol.Required(CONF_FEE_IN, default=d.get(CONF_FEE_IN, DEFAULTS[CONF_FEE_IN])):
            _num(0, 0.2, "any", "EUR/kWh"),
        vol.Required(CONF_FEE_OUT, default=d.get(CONF_FEE_OUT, DEFAULTS[CONF_FEE_OUT])):
            _num(0, 0.2, "any", "EUR/kWh"),
        vol.Required(CONF_NETTING_DEDUCTION,
                     default=d.get(CONF_NETTING_DEDUCTION, DEFAULTS[CONF_NETTING_DEDUCTION])):
            _num(0, 0.2, "any", "EUR/kWh"),
        vol.Required(CONF_VAT_PCT, default=d.get(CONF_VAT_PCT, DEFAULTS[CONF_VAT_PCT])):
            _num(0, 30, 0.1, "%"),
    })


def _opt(key: str, d: dict):
    """Optioneel veld; bestaande waarde als suggestie zodat hij leeg te maken is."""
    return vol.Optional(key, description={"suggested_value": d.get(key)})


def _solar_schema(d: dict) -> vol.Schema:
    return vol.Schema({
        _opt(CONF_PV_REMAINING, d): _ent(domain="sensor", device_class="energy"),
    })


def _usage_schema(d: dict) -> vol.Schema:
    return vol.Schema({
        _opt(CONF_EV_POWER, d): _ent(domain="sensor", device_class="power"),
        _opt(CONF_HOLIDAY, d): _ent(domain=["input_boolean", "switch", "binary_sensor"]),
        vol.Required(CONF_HOLIDAY_FACTOR,
                     default=d.get(CONF_HOLIDAY_FACTOR, DEFAULTS[CONF_HOLIDAY_FACTOR])):
            _num(0, 1, 0.05),
        vol.Required(CONF_YEARLY_KWH, default=d.get(CONF_YEARLY_KWH, DEFAULTS[CONF_YEARLY_KWH])):
            _num(500, 20000, 100, "kWh"),
    })


class AlphaEssOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if not self.hass.config_entries.async_entries(ALPHAESS_DOMAIN):
            return self.async_abort(reason="alphaess_missing")
        if user_input is not None:
            device_id = user_input[CONF_DEVICE]
            found = find_alphaess_entities(self.hass, device_id)
            missing = [k for k in ("soc", "capacity", "house_load") if k not in found]
            if missing:
                errors["base"] = "entities_not_found"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                device = dr.async_get(self.hass).async_get(device_id)
                self._data.update(user_input)
                self._data.update({CONF_SOC: found["soc"], CONF_CAPACITY: found["capacity"],
                                   CONF_HOUSE_LOAD: found["house_load"]})
                self._data["_title"] = (device.name_by_user or device.name) if device else "AlphaESS"
                return await self.async_step_prices()
        schema = vol.Schema({
            vol.Required(CONF_DEVICE): sel.DeviceSelector(
                sel.DeviceSelectorConfig(integration=ALPHAESS_DOMAIN)),
        }).extend(_battery_schema({}).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self.hass.config_entries.async_entries(NORDPOOL_DOMAIN):
            return self.async_abort(reason="nordpool_missing")
        errors: dict[str, str] = {}
        if user_input is not None:
            st = self.hass.states.get(user_input[CONF_PRICE])
            if st is None or "raw_today" not in st.attributes:
                errors[CONF_PRICE] = "no_raw_today"
            else:
                self._data.update(user_input)
                return await self.async_step_solar()
        return self.async_show_form(step_id="prices", data_schema=_price_schema(self._data),
                                    errors=errors)

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_usage()
        return self.async_show_form(step_id="solar", data_schema=_solar_schema(self._data))

    async def async_step_usage(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            title = f"Optimizer {self._data.pop('_title')}"
            return self.async_create_entry(title=title, data=self._data)
        return self.async_show_form(step_id="usage", data_schema=_usage_schema(self._data))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptimizerOptionsFlow()


class OptimizerOptionsFlow(OptionsFlow):
    """Alles behalve de omvormer opnieuw instellen."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] = {}

    def _cur(self) -> dict:
        return {**self.config_entry.data, **self.config_entry.options, **self._opts}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._opts.update(user_input)
            return await self.async_step_prices()
        return self.async_show_form(step_id="init", data_schema=_battery_schema(self._cur()))

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._opts.update(user_input)
            return await self.async_step_solar()
        return self.async_show_form(step_id="prices", data_schema=_price_schema(self._cur()))

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # leeggemaakt optioneel veld komt niet mee: expliciet wissen
            self._opts[CONF_PV_REMAINING] = user_input.get(CONF_PV_REMAINING)
            return await self.async_step_usage()
        return self.async_show_form(step_id="solar", data_schema=_solar_schema(self._cur()))

    async def async_step_usage(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._opts.update(user_input)
            self._opts[CONF_EV_POWER] = user_input.get(CONF_EV_POWER)
            self._opts[CONF_HOLIDAY] = user_input.get(CONF_HOLIDAY)
            return self.async_create_entry(data=self._opts)
        return self.async_show_form(step_id="usage", data_schema=_usage_schema(self._cur()))
