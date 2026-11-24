"""Salderingsregime: 2026 (saldering) of 2027 (geen saldering)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import OptimizerConfigEntry
from .const import KEY_REGIME, REGIMES, RUNTIME_DEFAULTS
from .entity import OptimizerEntity


async def async_setup_entry(hass: HomeAssistant, entry: OptimizerConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([RegimeSelect(entry.runtime_data)])


class RegimeSelect(OptimizerEntity, SelectEntity, RestoreEntity):
    _attr_options = REGIMES
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, KEY_REGIME)
        self._attr_current_option = RUNTIME_DEFAULTS[KEY_REGIME]

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in REGIMES:
            self._attr_current_option = last.state
        await self.coordinator.async_set_setting(KEY_REGIME, self._attr_current_option)

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()
        await self.coordinator.async_set_setting(KEY_REGIME, option)
