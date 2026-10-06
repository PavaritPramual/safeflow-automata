"""Deterministic one-room RC model. All defaults are synthetic fixture values."""
import math
from dataclasses import asdict, dataclass
from .commands import Command, MODES, validate_command


@dataclass(frozen=True)
class Physics:
    thermal_capacity_j_per_k: float = 3_000_000
    envelope_conductance_w_per_k: float = 120
    fan_conductance_w_per_k: float = 80
    cooling_heat_w: float = 3000
    heating_heat_w: float = 2000
    ac_electrical_w: float = 1000
    heater_electrical_w: float = 2000
    fan_electrical_w: float = 50
    light_electrical_w: float = 20

    def __post_init__(self):
        values = asdict(self)
        if any(not math.isfinite(x) or x < 0 for x in values.values()):
            raise ValueError("invalid_physics_parameter")
        if self.thermal_capacity_j_per_k <= 0:
            raise ValueError("capacity_must_be_positive")


class Home:
    def __init__(self, physics=None):
        self.physics = physics or Physics()
        self.reset()

    def reset(self, scenario=None):
        scenario = scenario or {}
        self.time_s = 0.0
        self.temperature_c = self._finite(scenario.get("temperature_c", 30))
        self.outdoor_c = self._finite(scenario.get("outdoor_c", 32))
        self.target_c = self._finite(scenario.get("target_c", 25))
        self.light_required = scenario.get("light_required", False)
        if not isinstance(self.light_required, bool):
            raise ValueError("light_required_must_be_boolean")
        self.devices = {d: "off" for d in MODES}
        for d, mode in scenario.get("devices", {}).items():
            validate_command(Command("set_device", d, mode))
            self.devices[d] = mode
        self.last_ac_off_s = None  # None means initially ready, not a false cooldown.
        self.energy_wh = 0.0
        return self.snapshot()

    @staticmethod
    def _finite(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("finite_numeric_value_required")
        return float(value)

    def set_goals(self, target_c=None, light_required=None):
        if target_c is not None:
            value = self._finite(target_c)
            if not 10 <= value <= 40:
                raise ValueError("target_out_of_range")
            self.target_c = value
        if light_required is not None:
            if not isinstance(light_required, bool):
                raise ValueError("light_required_must_be_boolean")
            self.light_required = light_required

    def power_w(self):
        p = self.physics
        return (p.ac_electrical_w * (self.devices["air_conditioner"] == "cool")
                + p.heater_electrical_w * (self.devices["heater"] == "on")
                + p.fan_electrical_w * (self.devices["ventilation_fan"] == "on")
                + p.light_electrical_w * (self.devices["light"] == "on"))

    def snapshot(self):
        return {
            "simulation_time_s": self.time_s, "temperature_c": self.temperature_c,
            "outdoor_c": self.outdoor_c, "target_c": self.target_c,
            "light_required": self.light_required, "devices": dict(self.devices),
            "ac_off_elapsed_s": None if self.last_ac_off_s is None else self.time_s - self.last_ac_off_s,
            "power_w": self.power_w(), "energy_wh": self.energy_wh,
        }

    def apply(self, command):
        validate_command(command)
        if command.name == "set_device":
            if command.device == "air_conditioner" and self.devices[command.device] == "cool" and command.mode == "off":
                self.last_ac_off_s = self.time_s
            self.devices[command.device] = command.mode
        return self.snapshot()

    def advance(self, seconds=30):
        seconds = self._finite(seconds)
        if seconds < 0:
            raise ValueError("negative_time")
        p = self.physics
        # Fan exchanges room/outdoor air; it is not treated as an AC.
        ua = p.envelope_conductance_w_per_k + p.fan_conductance_w_per_k * (self.devices["ventilation_fan"] == "on")
        heat = (p.heating_heat_w * (self.devices["heater"] == "on")
                - p.cooling_heat_w * (self.devices["air_conditioner"] == "cool")
                + p.light_electrical_w * (self.devices["light"] == "on"))
        if ua == 0:
            self.temperature_c += heat * seconds / p.thermal_capacity_j_per_k
        else:
            equilibrium = self.outdoor_c + heat / ua
            self.temperature_c = equilibrium + (self.temperature_c - equilibrium) * math.exp(-ua * seconds / p.thermal_capacity_j_per_k)
        self.energy_wh += self.power_w() * seconds / 3600
        self.time_s += seconds
        return self.snapshot()
