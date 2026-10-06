"""Home Assistant talks only to SafeFlow's authenticated proposal API."""
from datetime import timedelta
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

    async def request(self, path, data=None):
        async with self.session.request("GET" if data is None else "POST",
                self.url + path, headers=self.headers, json=data,
                timeout=aiohttp.ClientTimeout(total=150)) as response:
            response.raise_for_status()
            return await response.json()

    async def _async_update_data(self):
        try:
            return await self.request("/state")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise UpdateFailed("SafeFlow backend unavailable") from exc


async def async_setup(hass, config):
    coordinator = SafeFlowCoordinator(hass, config[DOMAIN])
    hass.data[DOMAIN] = coordinator
    await coordinator.async_refresh()
    await asyncio.gather(*(discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
                           for platform in ("sensor", "switch", "number", "button")))
    return True
