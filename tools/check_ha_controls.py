"""Run in the installed HA container: pipe this file to docker exec -i ... python -."""
import asyncio
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0, "/config")
from homeassistant.exceptions import HomeAssistantError
from custom_components.safeflow import SafeFlowCoordinator
from custom_components.safeflow.button import SafeFlowButton, DEVICES
from custom_components.safeflow.select import LightGoal


class UIContracts(unittest.IsolatedAsyncioTestCase):
    def coordinator(self, request):
        c = object.__new__(SafeFlowCoordinator)
        c.ui_busy = False; c.ui_error = c.ui_notice = None
        c.data = {"readiness": "ready", "pending_requests": 0}
        c.last_update_success = True
        c.request = request
        c.signals = []
        c.async_update_listeners = lambda: c.signals.append(c.ui_busy)
        c.async_set_updated_data = lambda value: setattr(c, "data", value)
        return c

    async def test_busy_rejects_duplicates_and_disables_controls(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def request(path, data=None):
            calls.append(path)
            if path == "/step":
                entered.set(); await release.wait()
            return {"readiness": "ready", "pending_requests": 0}
        c = self.coordinator(request)
        task = asyncio.create_task(c.perform("/step", {}, "working"))
        await entered.wait()
        self.assertTrue(c.ui_busy)
        self.assertFalse(SafeFlowButton(c, "step").available)
        self.assertFalse(SafeFlowButton(c, "request", "light", True).available)
        self.assertFalse(LightGoal(c).available)
        with self.assertRaises(HomeAssistantError):
            await c.perform("/step", {}, "duplicate")
        release.set(); await task
        self.assertEqual(calls, ["/step", "/state"])
        self.assertEqual(c.signals, [True, False])
        self.assertTrue(SafeFlowButton(c, "step").available)

    async def test_failed_request_is_not_retried_and_unlocks(self):
        calls = []
        async def request(path, data=None):
            calls.append(path); raise asyncio.TimeoutError()
        c = self.coordinator(request)
        with self.assertRaises(HomeAssistantError):
            await c.perform("/human", {"device": "light", "mode": "on"}, "sending")
        self.assertEqual(calls, ["/human"])
        self.assertFalse(c.ui_busy)
        self.assertIsNotNone(c.ui_error)

    async def test_explicit_requests_are_independent_of_observed_state(self):
        calls = []
        async def perform(path, data, notice): calls.append((path, data))
        c = SimpleNamespace(perform=perform, data={"devices": {k: "on" for k in DEVICES}})
        for device in DEVICES:
            for on in (True, False):
                b = SafeFlowButton(c, "request", device, on)
                await b.async_press()
                mode = "cool" if on and device == "air_conditioner" else "on" if on else "off"
                self.assertEqual(calls[-1], ("/human", {"device": device, "mode": mode}))
        self.assertEqual(len(calls), 8)
        await LightGoal(c).async_select_option("อยากให้ไฟเปิด")
        self.assertEqual(calls[-1], ("/goals", {"light_required": True}))
        await LightGoal(c).async_select_option("อยากให้ไฟปิด")
        self.assertEqual(calls[-1], ("/goals", {"light_required": False}))


if __name__ == "__main__": unittest.main(verbosity=2)
