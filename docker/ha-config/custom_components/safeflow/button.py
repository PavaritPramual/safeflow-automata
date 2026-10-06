from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([SafeFlowButton(hass.data[DOMAIN], action) for action in ("step", "reset")])


class SafeFlowButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, action):
        super().__init__(coordinator)
        self.action = action
        self._attr_name = "SafeFlow " + ("Run one round" if action == "step" else "Reset episode")
        self._attr_unique_id = "safeflow_" + action
        self.entity_id = "button.safeflow_" + action

    async def async_press(self):
        await self.coordinator.request("/" + self.action, {})
        await self.coordinator.async_request_refresh()
