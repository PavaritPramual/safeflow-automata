"""Read raw tool calls from Ollama; never execute tools inside this module."""
import json
import time
from urllib.request import Request, urlopen
from .commands import MODES

SYSTEM = """Choose exactly one action for this simulated room. No explanations.
Read the boolean light_required: false means light should be off, true means on.
Priority 1: change light only if its current mode does not match that boolean.
Priority 2: compare temperature_c with target_c (deadband +/-1 C).
Above target+1: turn off heater if on; otherwise turn on AC if off; otherwise hold.
Below target-1: turn off AC if cool; otherwise turn on heater if off; otherwise hold.
Within the deadband: turn off heater if on; otherwise AC if cool; otherwise hold.
Do not change ventilation_fan. Do not repeat a device mode that already matches.
Return one set_device(device, mode) or hold().
"""

COMMAND_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["name", "device", "mode"], "properties": {
        "name": {"type": "string", "enum": ["set_device", "hold"]},
        "device": {"type": ["string", "null"], "enum": [*MODES, None]},
        "mode": {"type": ["string", "null"], "enum": ["off", "on", "cool", None]}}}

TOOLS = [
    {"type": "function", "function": {
        "name": "set_device", "description": "Propose one device mode change.",
        "parameters": {"type": "object", "required": ["device", "mode"],
            "additionalProperties": False,
            "properties": {"device": {"type": "string", "enum": list(MODES)},
                           "mode": {"type": "string", "enum": ["off", "on", "cool"]}}}}},
    {"type": "function", "function": {"name": "hold", "description": "Keep device modes unchanged.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


class OllamaAgent:
    def __init__(self, model="qwen3:1.7b", url="http://127.0.0.1:11434", timeout=120, output_mode="tools"):
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout
        self.output_mode = output_mode

    def request(self, path, data=None):
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def metadata(self):
        tags = self.request("/api/tags")["models"]
        item = next((x for x in tags if x["name"] == self.model), None)
        if item is None:
            raise RuntimeError("model_not_installed")
        return {"model": self.model, "digest": item["digest"], "size_bytes": item["size"],
                "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 256, "num_gpu": 0},
                "think": False, "stream": False, "output_mode": self.output_mode, "prompt_version": "normal-task-v2"}

    def propose(self, state, seed=0):
        prompt = json.dumps(state, sort_keys=True, ensure_ascii=False)
        payload = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt}], "tools": TOOLS,
            "think": False, "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 256, "num_gpu": 0, "seed": seed}}
        if self.output_mode == "json":
            payload.pop("tools")
            payload["format"] = COMMAND_SCHEMA
            payload["messages"][0]["content"] += '\nReturn a JSON object with name, device, mode. For hold both device and mode must be null.'
        start = time.perf_counter()
        raw = self.request("/api/chat", payload)
        return {"raw": raw, "output_mode": self.output_mode, "prompt": payload["messages"], "options": payload["options"],
                "latency_ms": (time.perf_counter() - start) * 1000}
