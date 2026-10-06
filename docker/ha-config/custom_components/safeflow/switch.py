from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]
    async_add_entities([SafeFlowSwitch(coordinator, device) for device in
        ("air_conditioner", "heater", "ventilation_fan", "light", "light_required")])


class SafeFlowSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device):
        super().__init__(coordinator)
        self.device = device
        self._attr_name = "SafeFlow " + device.replace("_", " ")
        self._attr_unique_id = "safeflow_" + device
        self.entity_id = "switch.safeflow_" + device

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        if self.device == "light_required":
            return data.get("light_required", False)
        return data.get("devices", {}).get(self.device, "off") != "off"

    async def set_mode(self, on):
        if self.device == "light_required":
            await self.coordinator.request("/goals", {"light_required": on})
        else:
            mode = "cool" if on and self.device == "air_conditioner" else "on" if on else "off"
            await self.coordinator.request("/human", {"device": self.device, "mode": mode})
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs):
        await self.set_mode(True)

    async def async_turn_off(self, **kwargs):
        await self.set_mode(False)
