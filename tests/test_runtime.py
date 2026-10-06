import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from safeflow.commands import Command, decode_response
from safeflow.controller import Controller
from safeflow.environment import Home, Physics
from safeflow.server import make_server
from safeflow.trace import Trace, replay


def response(device="air_conditioner", mode="cool"):
    return {"message": {"tool_calls": [{"function": {"name": "set_device",
            "arguments": {"device": device, "mode": mode}}}]}}


class Agent:
    def metadata(self):
        return {"model": "fixture-only"}

    def propose(self, state, seed=0):
        return {"raw": response(), "prompt": state, "latency_ms": 0}


class PhysicsTests(unittest.TestCase):
    def test_passive_analytic_solution(self):
        home = Home()
        home.reset({"temperature_c": 20, "outdoor_c": 30})
        expected = 30 - 10 * math.exp(-120 * 3600 / 3_000_000)
        self.assertAlmostEqual(home.advance(3600)["temperature_c"], expected, places=12)

    def test_constant_heat_without_conduction(self):
        home = Home(Physics(envelope_conductance_w_per_k=0))
        home.reset({"temperature_c": 20, "devices": {"heater": "on"}})
        self.assertAlmostEqual(home.advance(60)["temperature_c"], 20.04)
        self.assertAlmostEqual(home.energy_wh, 2000 / 60)

    def test_time_partition_invariant(self):
        a, b = Home(), Home()
        for home in (a, b):
            home.apply(Command("set_device", "air_conditioner", "cool"))
        a.advance(300)
        for _ in range(10):
            b.advance(30)
        self.assertAlmostEqual(a.temperature_c, b.temperature_c, places=11)
        self.assertAlmostEqual(a.energy_wh, b.energy_wh, places=11)

    def test_fan_warms_room_when_outdoors_hotter(self):
        a, b = Home(), Home()
        b.apply(Command("set_device", "ventilation_fan", "on"))
        self.assertGreater(b.advance(30)["temperature_c"], a.advance(30)["temperature_c"])

    def test_repeated_off_does_not_reset_clock(self):
        home = Home()
        home.apply(Command("set_device", "air_conditioner", "cool"))
        home.apply(Command("set_device", "air_conditioner", "off"))
        home.advance(30)
        home.apply(Command("set_device", "air_conditioner", "off"))
        self.assertEqual(home.snapshot()["ac_off_elapsed_s"], 30)

    def test_reject_nonfinite_and_negative_time(self):
        for value in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(ValueError):
                Home().advance(value)

    def test_physics_parameter_validation(self):
        with self.assertRaises(ValueError):
            Physics(thermal_capacity_j_per_k=0)

    def test_no_shield_claim(self):
        home = Home()
        home.apply(Command("set_device", "heater", "on"))
        home.apply(Command("set_device", "air_conditioner", "cool"))
        self.assertEqual(home.power_w(), 3000)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "trace.jsonl"
        self.controller = Controller(Home(), Agent(), Trace(self.path))

    def records(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_proposal_and_decision_precede_apply(self):
        original = self.controller.home.apply
        def checked(command):
            records = self.records()
            self.assertEqual([r["event"] for r in records[-2:]], ["proposal", "decision"])
            return original(command)
        self.controller.home.apply = checked
        self.controller.step()

    def test_log_failure_prevents_execution_and_halts(self):
        before = self.controller.home.snapshot()
        self.controller.trace.write = lambda event: (_ for _ in ()).throw(OSError("disk full"))
        with self.assertRaises(OSError):
            self.controller.step()
        self.assertEqual(before, self.controller.home.snapshot())
        self.assertTrue(self.controller.halted)
        with self.assertRaises(RuntimeError):
            self.controller.step()

    def test_decision_log_failure_also_prevents_execution(self):
        writer = self.controller.trace.write
        def fail_decision(event):
            if event["event"] == "decision":
                raise OSError("disk full")
            writer(event)
        self.controller.trace.write = fail_decision
        with self.assertRaises(OSError):
            self.controller.step()
        self.assertEqual(self.controller.home.time_s, 0)
        self.assertEqual(self.controller.home.devices["air_conditioner"], "off")

    def test_human_fifo_then_ai_resumes(self):
        for device in ("light", "ventilation_fan"):
            self.controller.enqueue(response(device, "on")["message"]["tool_calls"][0])
        self.assertEqual(self.controller.step()["last_result"]["source"], "human")
        self.assertEqual(self.controller.step()["last_result"]["source"], "human")
        self.assertEqual(self.controller.step()["last_result"]["source"], "ai")
        self.assertEqual(self.controller.home.devices["light"], "on")

    def test_invalid_proposal_never_changes_device(self):
        self.controller.enqueue(response("unknown", "on")["message"]["tool_calls"][0])
        result = self.controller.step()
        self.assertEqual(result["last_result"]["validation"], "invalid")
        self.assertTrue(all(x == "off" for x in self.controller.home.devices.values()))
        self.assertEqual(self.controller.home.time_s, 30)

    def test_model_failure_is_logged_as_invalid(self):
        self.controller.agent.propose = lambda *args: (_ for _ in ()).throw(TimeoutError())
        self.assertEqual(self.controller.step()["last_result"]["reason"], "TimeoutError")
        self.assertEqual(self.records()[-3]["validation"], "invalid")

    def test_environment_failure_halts(self):
        self.controller.home.apply = lambda cmd: (_ for _ in ()).throw(RuntimeError("sim failed"))
        with self.assertRaises(RuntimeError):
            self.controller.step()
        self.assertTrue(self.controller.halted)

    def test_goals_and_reset_replay(self):
        self.controller.goals({"target_c": 24, "light_required": True})
        self.controller.step()
        self.controller.reset({"temperature_c": 18})
        self.controller.step()
        self.assertEqual(replay(self.records(), Home()), self.controller.home.snapshot())

    def test_execution_without_proposal_rejected(self):
        with self.assertRaises(ValueError):
            replay([{"event": "execution", "proposal_id": "missing"}], Home())

    def test_invalid_reset_does_not_change_home_or_trace(self):
        before, count = self.controller.home.snapshot(), len(self.records())
        with self.assertRaises(ValueError):
            self.controller.reset({"temperature_c": float("nan")})
        self.assertEqual(self.controller.home.snapshot(), before)
        self.assertEqual(len(self.records()), count)

    def test_nondefault_physics_is_recorded_for_replay(self):
        self.controller.home.physics = Physics(thermal_capacity_j_per_k=1000000)
        self.controller.reset()
        self.controller.step()
        self.assertEqual(replay(self.records(), Home()), self.controller.home.snapshot())

    def test_reject_multiple_calls_and_prose(self):
        raw = response()
        raw["message"]["tool_calls"] *= 2
        for value in (raw, {"message": {"content": "turn on AC"}}, None):
            with self.assertRaises(ValueError):
                decode_response(value)

    def test_real_http_auth_and_queue(self):
        server = make_server(self.controller, "x" * 32, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        with self.assertRaises(HTTPError) as caught:
            urlopen(url + "/state")
        self.assertEqual(caught.exception.code, 401)
        req = Request(url + "/human", data=b'{"device":"light","mode":"on"}',
                      headers={"Authorization": "Bearer " + "x" * 32})
        with urlopen(req) as res:
            self.assertEqual(res.status, 202)
        self.assertEqual(self.controller.home.devices["light"], "off")
        self.assertEqual(self.controller.step()["last_result"]["source"], "human")


if __name__ == "__main__":
    unittest.main()
