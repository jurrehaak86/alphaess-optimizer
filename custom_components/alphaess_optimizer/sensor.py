"""Sensoren: de actie van nu, de volgende momenten en diagnostiek."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import OptimizerConfigEntry
from .entity import OptimizerEntity
from .planner import moment_text

ACTION_OPTIONS = ["charge", "discharge", "balance", "hold"]
ACTION_ATTRS = (
    "reason", "soc_now", "expected_soc_end_of_quarter", "ceiling_pct", "reserve_pct",
    "charge_power_kw", "bms_charge_power_w",
    "strategy", "aggressiveness", "sell_threshold_eur_kwh", "hold_allowed", "cycle_limit",
    "cycles_today", "cycles_planned_today", "regime", "energy_tax", "wear_eur_kwh",
    "price_now", "sell_price_now", "horizon_until", "tomorrow_known",
    "expected_cost_horizon", "dp_runs", "calc_time_s", "profile", "updated", "plan",
    "plan_quarters",
)


async def async_setup_entry(hass: HomeAssistant, entry: OptimizerConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([
        ActionSensor(c),
        NextSensor(c, "charge"), NextSensor(c, "discharge"), NextSensor(c, "hold"),
        PercentSensor(c, "reserve_pct"), PercentSensor(c, "ceiling_pct"),
    ])


class ActionSensor(OptimizerEntity, SensorEntity):
    """Besluit voor het huidige kwartier, met het volledige plan als attributen."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ACTION_OPTIONS
    _unrecorded_attributes = frozenset({"plan", "plan_quarters", "reason"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "action")

    @property
    def native_value(self):
        return self.coordinator.data.get("action") if self.coordinator.data else None

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {k: d[k] for k in ACTION_ATTRS if k in d}


class NextSensor(OptimizerEntity, SensorEntity):
    """Eerstvolgend blok van een actie, als leesbare tekst."""

    def __init__(self, coordinator, action: str) -> None:
        super().__init__(coordinator, f"next_{action}")
        self._action = action

    def _blk(self) -> dict:
        return ((self.coordinator.data or {}).get("next") or {}).get(self._action) or {}

    @property
    def native_value(self):
        b = self._blk()
        return moment_text(b.get("start"), b.get("end"), b.get("soc_target"), dt_util.now())

    @property
    def extra_state_attributes(self):
        return self._blk()


class PercentSensor(OptimizerEntity, SensorEntity):
    """Reserve en laadplafond zoals het plan ze nu gebruikt."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._key = key

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)
