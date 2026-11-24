"""Instellingen die je zonder herconfigureren aanpast (dashboard, automations)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptimizerConfigEntry
from .const import (
    KEY_AGGRESSIVENESS,
    KEY_BACKUP_TARGET,
    KEY_BACKUP_WEIGHT,
    KEY_ENERGY_TAX,
    KEY_WEAR,
    RUNTIME_DEFAULTS,
)
from .entity import OptimizerEntity


@dataclass(frozen=True, kw_only=True)
class OptNumberDescription(NumberEntityDescription):
    as_int: bool = False


NUMBERS = (
    OptNumberDescription(key=KEY_AGGRESSIVENESS, native_min_value=1, native_max_value=10,
                         native_step=1, mode=NumberMode.SLIDER, as_int=True),
    OptNumberDescription(key=KEY_BACKUP_TARGET, native_min_value=0, native_max_value=100,
                         native_step=1, native_unit_of_measurement=PERCENTAGE,
                         mode=NumberMode.SLIDER),
    OptNumberDescription(key=KEY_BACKUP_WEIGHT, native_min_value=0, native_max_value=8,
                         native_step=0.5, mode=NumberMode.SLIDER),
    OptNumberDescription(key=KEY_ENERGY_TAX, native_min_value=0, native_max_value=0.5,
                         native_step=0.0001, native_unit_of_measurement="EUR/kWh",
                         mode=NumberMode.BOX, entity_category=EntityCategory.CONFIG),
    OptNumberDescription(key=KEY_WEAR, native_min_value=0, native_max_value=0.2,
                         native_step=0.005, native_unit_of_measurement="EUR/kWh",
                         mode=NumberMode.BOX, entity_category=EntityCategory.CONFIG),
)


async def async_setup_entry(hass: HomeAssistant, entry: OptimizerConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(SettingNumber(entry.runtime_data, d) for d in NUMBERS)


class SettingNumber(OptimizerEntity, RestoreNumber):
    entity_description: OptNumberDescription

    def __init__(self, coordinator, description: OptNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_native_value = RUNTIME_DEFAULTS[description.key]

    @property
    def available(self) -> bool:
        return True   # een instelling blijft aanpasbaar, ook als het plan faalt

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        await self._push()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        await self._push()

    async def _push(self) -> None:
        v = self._attr_native_value
        if self.entity_description.as_int:
            v = int(round(v))
        await self.coordinator.async_set_setting(self.entity_description.key, v)
