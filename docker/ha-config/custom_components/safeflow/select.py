"""The desired light state is a goal, never an immediate device command."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([LightGoal(hass.data[DOMAIN])])


class LightGoal(CoordinatorEntity, SelectEntity):
    _attr_name = "เป้าหมายไฟให้ AI"
    _attr_unique_id = "safeflow_light_goal"
    _attr_options = ["อยากให้ไฟปิด", "อยากให้ไฟเปิด"]

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.entity_id = "select.safeflow_light_goal"

    @property
    def current_option(self):
        return self._attr_options[bool((self.coordinator.data or {}).get("light_required", False))]

    async def async_select_option(self, option):
        if option not in self._attr_options:
            raise ValueError("unknown_light_goal")
        await self.coordinator.perform("/goals", {"light_required": option == self._attr_options[1]}, "กำลังบันทึกเป้าหมายไฟ")

    @property
    def available(self):
        data = self.coordinator.data or {}
        return (super().available and not self.coordinator.ui_busy
                and data.get("readiness") == "ready" and not data.get("halted"))
