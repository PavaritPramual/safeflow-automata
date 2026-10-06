from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN

SENSORS = [
    ("temperature", "temperature_c", "°C"),
    ("power", "power_w", "W"),
    ("energy", "energy_wh", "Wh"),
    ("simulation_time", "simulation_time_s", "s"),
    ("pending", "pending_requests", None),
    ("status", "halted", None),
]


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([SafeFlowSensor(hass.data[DOMAIN], *spec) for spec in SENSORS])


class SafeFlowSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, slug, field, unit):
        super().__init__(coordinator)
        self._attr_name = "SafeFlow " + slug.replace("_", " ")
        self._attr_unique_id = "safeflow_" + slug
        self.entity_id = "sensor.safeflow_" + slug
        self._attr_native_unit_of_measurement = unit
        self.field = field

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self.field)
        return ("halted" if value else "unshielded") if self.field == "halted" else value

    @property
    def extra_state_attributes(self):
        if self.field != "halted":
            return None
        data = self.coordinator.data or {}
        return {"enforcement": data.get("enforcement"), "last_result": data.get("last_result"),
                "model": data.get("model", {}).get("model")}
