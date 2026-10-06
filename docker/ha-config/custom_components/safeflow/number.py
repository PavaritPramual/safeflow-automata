from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([TargetTemperature(hass.data[DOMAIN])])


class TargetTemperature(CoordinatorEntity, NumberEntity):
    _attr_name = "SafeFlow target temperature"
    _attr_unique_id = "safeflow_target_temperature"
    _attr_native_min_value = 10
    _attr_native_max_value = 40
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.entity_id = "number.safeflow_target_temperature"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("target_c")

    async def async_set_native_value(self, value):
        await self.coordinator.request("/goals", {"target_c": value})
        await self.coordinator.async_request_refresh()
