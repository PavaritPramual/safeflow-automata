"""Strict proposal decoding; no safety policy is applied here."""
from dataclasses import asdict, dataclass

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


def decode_response(response):
    message = response.get("message") if isinstance(response, dict) else None
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
