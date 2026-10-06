import json
import tempfile
import unittest
from pathlib import Path
from safeflow.automata import Automata
from safeflow.commands import Command, decode_response
from safeflow.controller import Controller
from safeflow.environment import Home
from safeflow.trace import Trace, replay
from test_runtime import Agent, response


class AutomataTests(unittest.TestCase):
    def test_boundaries_and_off_noop(self):
        for elapsed in (0, 30, 179, 180, 181, 210):
            home = Home()
            home.apply(Command("set_device", "air_conditioner", "cool"))
            home.apply(Command("set_device", "air_conditioner", "off"))
            home.advance(elapsed)
            home.apply(Command("set_device", "air_conditioner", "off"))
            guard = Automata(); guard.reset(home.snapshot())
            outcome = guard.evaluate(Command("set_device", "air_conditioner", "cool"), "ai", home.snapshot()).outcome
            self.assertEqual(outcome, "allow" if elapsed >= 180 else "block")

    def test_all_device_states_sources_and_commands(self):
        # An independent oracle for the finite action/state domain, not an LLM.
        for ac in (False, True):
            for heat in (False, True):
                for elapsed in (None, 0, 179, 180, 181):
                    for source in ("human", "ai"):
                        for command in [Command("hold"), *[Command("set_device", d, m)
                                        for d, modes in __import__('safeflow.commands', fromlist=['MODES']).MODES.items() for m in modes]]:
                            home = Home(); home.reset({"devices": {"air_conditioner": "cool" if ac else "off", "heater": "on" if heat else "off"}})
                            home.time_s = 200; home.last_ac_off_s = None if elapsed is None else 200-elapsed
                            guard = Automata(); guard.reset(home.snapshot())
                            denied = source == "ai" and ((command.device == "air_conditioner" and command.mode == "cool" and (heat or (not ac and elapsed is not None and elapsed < 180))) or (command.device == "heater" and command.mode == "on" and ac))
                            self.assertEqual(guard.evaluate(command, source, home.snapshot()).outcome, "human_bypass" if source == "human" else "block" if denied else "allow")

    def controller(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name)/"trace.jsonl"
        return Controller(Home(), Agent(), Trace(path)), path

    def test_block_keeps_devices_advances_and_replays(self):
        controller, path = self.controller()
        controller.reset({"devices": {"heater": "on"}})
        result = controller.step()
        self.assertEqual(result["last_result"]["decision"], "block")
        self.assertEqual(result["devices"]["air_conditioner"], "off")
        self.assertEqual(result["simulation_time_s"], 30)
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        self.assertEqual(replay(rows, Home()), controller.home.snapshot())

    def test_human_conflict_and_ai_resumption(self):
        controller, _ = self.controller()
        for d,m in (("air_conditioner","cool"),("heater","on")):
            controller.enqueue(response(d,m)["message"]["tool_calls"][0]); controller.step()
        self.assertTrue(controller.automata.state["ac"] and controller.automata.state["heater"])
        self.assertEqual(controller.step()["last_result"]["decision"], "block")
        self.assertFalse(controller.halted)
        controller.agent.propose = lambda *args: {"raw": response("heater", "off")}
        self.assertEqual(controller.step()["last_result"]["decision"], "allow")

    def test_human_off_and_immediate_reopen_updates_clock(self):
        controller, _ = self.controller(); controller.step()
        controller.enqueue(response("air_conditioner","off")["message"]["tool_calls"][0]); controller.step()
        self.assertEqual(controller.step()["last_result"]["decision"], "block")
        controller.enqueue(response()["message"]["tool_calls"][0])
        self.assertEqual(controller.step()["last_result"]["decision"], "human_bypass")
        self.assertEqual(controller.step()["last_result"]["decision"], "allow")

    def test_external_state_change_halts(self):
        controller, _ = self.controller()
        controller.home.devices["heater"] = "on"
        with self.assertRaises(ValueError): controller.step()
        self.assertTrue(controller.halted)

    def test_bad_execution_clock_halts(self):
        controller, _ = self.controller()
        original=controller.home.advance
        def broken(seconds):
            result=original(seconds); result["simulation_time_s"]+=1; return result
        controller.home.advance=broken
        with self.assertRaises(ValueError): controller.step()
        self.assertTrue(controller.halted)

    def test_json_is_parsed_without_repair(self):
        good={"message":{"content":'{"name":"hold","device":null,"mode":null}'}}
        self.assertEqual(decode_response(good,"json"),Command("hold"))
        for content in ('{}', '```json\n{}\n```', '[{}]', '{"name":"hold","device":"light","mode":"on"}'):
            with self.assertRaises(ValueError): decode_response({"message":{"content":content}},"json")

    def test_tampered_block_execution_rejected(self):
        controller,path=self.controller(); controller.reset({"devices":{"heater":"on"}}); controller.step()
        rows=[json.loads(x) for x in path.read_text().splitlines()]
        rows[-2]["decision"]="execute_unshielded"
        with self.assertRaises(ValueError): replay(rows,Home())

    def test_post_execution_log_failure_halts_without_retry(self):
        controller,_=self.controller(); writer=controller.trace.write
        def failed(event):
            if event["event"]=="execution": raise OSError("disk_full")
            writer(event)
        controller.trace.write=failed
        with self.assertRaises(OSError): controller.step()
        self.assertEqual(controller.home.devices["air_conditioner"],"cool")
        self.assertTrue(controller.halted)
        with self.assertRaises(RuntimeError): controller.step()

    def test_goal_change_cannot_hide_state_tamper(self):
        controller,_=self.controller(); controller.home.devices["heater"]="on"
        with self.assertRaises(ValueError): controller.goals({"target_c":24})
        self.assertTrue(controller.halted)

    def test_incomplete_trace_not_reported_as_replayed(self):
        controller,path=self.controller(); controller.step()
        rows=[json.loads(x) for x in path.read_text().splitlines()]
        with self.assertRaises(ValueError): replay(rows[:-1],Home())
