"""Strict proposal decoding; no safety policy is applied here."""
from dataclasses import asdict, dataclass
import json

MODES = {
    "air_conditioner": ("off", "cool"),
    "heater": ("off", "on"),
    "ventilation_fan": ("off", "on"),
    "light": ("off", "on"),
}


@dataclass(frozen=True)
class Command:
    name: str
    device: str | None = None
    mode: str | None = None

    def to_dict(self):
        return asdict(self)


def decode_call(call):
    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
        raise ValueError("invalid_tool_call")
    fn = call["function"]
    name, args = fn.get("name"), fn.get("arguments")
    if not isinstance(args, dict):
        raise ValueError("arguments_must_be_object")
    if name == "hold" and not args:
        return Command("hold")
    if name != "set_device" or set(args) != {"device", "mode"}:
        raise ValueError("unknown_tool_or_arguments")
    device, mode = args["device"], args["mode"]
    if not isinstance(device, str) or device not in MODES:
        raise ValueError("unknown_device")
    if not isinstance(mode, str) or mode not in MODES[device]:
        raise ValueError("unsupported_mode")
    return Command(name, device, mode)


def decode_response(response, output_mode="tools"):
    message = response.get("message") if isinstance(response, dict) else None
    if output_mode == "json":
        try:
            value = json.loads(message["content"])
            if not isinstance(value, dict) or set(value) != {"name", "device", "mode"}:
                raise ValueError("invalid_json_command")
            if value["name"] == "hold" and (value["device"] is not None or value["mode"] is not None):
                raise ValueError("invalid_hold_arguments")
            return decode_call({"function": {"name": value["name"], "arguments": {} if value["name"] == "hold" else {"device": value["device"], "mode": value["mode"]}}})
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json_command") from exc
    if output_mode != "tools":
        raise ValueError("unknown_output_mode")
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(calls, list) or len(calls) != 1:
        raise ValueError("exactly_one_tool_call_required")
    return decode_call(calls[0])


def validate_command(command):
    return decode_call({"function": {
        "name": command.name,
        "arguments": {} if command.name == "hold" else {
            "device": command.device, "mode": command.mode},
    }})
