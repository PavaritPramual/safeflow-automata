"""Momentary requests are separate from observed appliance state."""
import uuid
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN

DEVICES = {"air_conditioner": "แอร์", "heater": "ฮีเตอร์",
           "ventilation_fan": "พัดลมระบายอากาศ", "light": "ไฟ"}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]
    entities = [SafeFlowButton(coordinator, action) for action in ("step", "reset")]
    entities.extend(SafeFlowButton(coordinator, "request", device, on)
                    for device in DEVICES for on in (True, False))
    async_add_entities(entities)


class SafeFlowButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, action, device=None, on=None):
        super().__init__(coordinator)
        self.action, self.device, self.on = action, device, on
        slug = action if action != "request" else "request_" + device + ("_on" if on else "_off")
        self._attr_name = ("ขอ" + ("เปิด" if on else "ปิด") + DEVICES[device]) if action == "request" else {"step": "ทำงาน 1 รอบ", "reset": "เริ่มการทดลองใหม่"}[action]
        self._attr_unique_id = "safeflow_" + slug
        self.entity_id = "button.safeflow_" + slug

    async def async_press(self):
        if self.action == "request":
            mode = "cool" if self.on and self.device == "air_conditioner" else "on" if self.on else "off"
            await self.coordinator.perform("/human", {"device": self.device, "mode": mode}, "กำลังส่งคำขอของคน")
        else:
            payload = {"request_id": str(uuid.uuid4())} if self.action == "step" else {}
            notice = "กำลังทำงาน กรุณารอ ผลที่แสดงยังเป็นรอบก่อนหน้า" if self.action == "step" else "กำลังเริ่มการทดลองใหม่"
            await self.coordinator.perform("/" + self.action, payload, notice)

    @property
    def available(self):
        data = self.coordinator.data or {}
        return (super().available and not self.coordinator.ui_busy and data.get("readiness") == "ready"
                and (self.action == "reset" or not data.get("halted")))
