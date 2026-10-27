"""Home Assistant talks only to SafeFlow's authenticated proposal API."""
from datetime import timedelta
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError

DOMAIN = "safeflow"
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({vol.Required("url"): cv.url,
    vol.Required("api_key"): cv.string})}, extra=vol.ALLOW_EXTRA)


class SafeFlowCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, options):
        super().__init__(hass, logger=__import__("logging").getLogger(__name__),
                         name=DOMAIN, update_interval=timedelta(seconds=5))
        self.session = async_get_clientsession(hass)
        self.url = options["url"].rstrip("/")
        self.headers = {"Authorization": "Bearer " + options["api_key"]}
        self.ui_busy = False
        self.ui_notice = None
        self.ui_error = None

    async def perform(self, path, data, notice):
        """One UI operation at a time; uncertain failures never auto-retry."""
        if self.ui_busy:
            raise HomeAssistantError("กำลังทำงานอยู่ กรุณารอให้เสร็จก่อน")
        self.ui_busy, self.ui_error, self.ui_notice = True, None, notice
        self.async_update_listeners()
        try:
            result = await self.request(path, data)
            # /human returns a queue receipt, other operations return a snapshot.
            if path != "/human":
                self.async_set_updated_data(result)
            self.async_set_updated_data(await self.request("/state"))
            self.ui_notice = {
                "/human": "ส่งคำขอเข้าคิวแล้ว กดทำงาน 1 รอบเพื่อนำไปใช้",
                "/goals": "บันทึกเป้าหมายแล้ว เป้าหมายจะถูกส่งให้ AI ในรอบ AI ถัดไป",
                "/step": "ทำงานเสร็จแล้ว อ่านผลและสถานะบ้านด้านล่าง",
                "/reset": "เริ่มบ้านจำลองและรอบการทดลองใหม่แล้ว",
            }.get(path)
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            self.ui_error = "ติดต่อบริการไม่สำเร็จ ผลคำขออาจยังไม่แน่นอน รออ่านสถานะกลับก่อนส่งซ้ำ"
            self.ui_notice = None
            raise HomeAssistantError(self.ui_error) from exc
        finally:
            self.ui_busy = False
            self.async_update_listeners()

    async def request(self, path, data=None):
        async with self.session.request("GET" if data is None else "POST",
                self.url + path, headers=self.headers, json=data,
                timeout=aiohttp.ClientTimeout(total=150)) as response:
            response.raise_for_status()
            return await response.json()

    async def _async_update_data(self):
        if self.ui_busy and self.data is not None:
            return self.data
        try:
            return await self.request("/state")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise UpdateFailed("SafeFlow backend unavailable") from exc


async def async_setup(hass, config):
    coordinator = SafeFlowCoordinator(hass, config[DOMAIN])
    hass.data[DOMAIN] = coordinator
    await coordinator.async_refresh()
    await asyncio.gather(*(discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
                           for platform in ("sensor", "switch", "number", "button", "select")))
    return True
