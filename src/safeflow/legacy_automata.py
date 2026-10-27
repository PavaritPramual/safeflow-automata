"""Policy automata; the environment deliberately remains permissive."""
import math
from dataclasses import dataclass
from .commands import MODES, validate_command

POLICY_VERSION = "smart-home-v1"
COOLDOWN_S = 180


def abstract(snapshot):
    devices = snapshot["devices"]
    if set(devices) != set(MODES) or any(devices[d] not in MODES[d] for d in MODES):
        raise ValueError("unknown_observed_state")
    now, elapsed = snapshot["simulation_time_s"], snapshot["ac_off_elapsed_s"]
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
        raise ValueError("invalid_observed_time")
    if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                                or not math.isfinite(elapsed) or not 0 <= elapsed <= now):
        raise ValueError("invalid_observed_clock")
    return {"ac": devices["air_conditioner"] == "cool", "heater": devices["heater"] == "on",
            "cooldown": "ready" if elapsed is None or elapsed >= COOLDOWN_S else "resting",
            "elapsed_s": elapsed, "time_s": now}


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str | None = None


class Automata:
    def reset(self, snapshot):
        self.state = abstract(snapshot)
        self.expected = snapshot.copy()

    def evaluate(self, command, source, snapshot):
        state = abstract(snapshot)
        if snapshot != self.expected:
            raise ValueError("automata_state_mismatch")
        if source not in ("ai", "human"):
            raise ValueError("unknown_command_source")
        if command is None:
            return Decision("reject_invalid", "invalid_proposal")
        validate_command(command)
        if source == "human":
            return Decision("human_bypass")
        if command.name == "set_device":
            if ((command.device == "air_conditioner" and command.mode == "cool" and state["heater"])
                    or (command.device == "heater" and command.mode == "on" and state["ac"])):
                return Decision("block", "ac_heater_conflict")
            if (command.device == "air_conditioner" and command.mode == "cool"
                    and not state["ac"] and state["cooldown"] == "resting"):
                return Decision("block", "ac_cooldown")
        return Decision("allow")

    def observe(self, before, command, after, advance_s):
        # Independently predict the actual effect, including duplicate off and human bypass.
        if before != self.expected:
            raise ValueError("automata_state_mismatch")
        devices = dict(before["devices"])
        elapsed = before["ac_off_elapsed_s"]
        if command and command.name == "set_device":
            if command.device == "air_conditioner" and devices[command.device] == "cool" and command.mode == "off":
                elapsed = 0
            devices[command.device] = command.mode
        if after["devices"] != devices or after["simulation_time_s"] != before["simulation_time_s"] + advance_s:
            raise ValueError("unexpected_environment_transition")
        expected_elapsed = None if elapsed is None else elapsed + advance_s
        if after["ac_off_elapsed_s"] != expected_elapsed:
            raise ValueError("unexpected_clock_transition")
        self.state = abstract(after)
        self.expected = after.copy()
