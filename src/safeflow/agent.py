"""Read raw tool calls from Ollama; never execute tools inside this module."""
import json
import time
from urllib.request import Request, urlopen
from .commands import MODES

SYSTEM = """You control a simulated room. Return exactly ONE tool call and no prose.
Choose one useful action per turn, using the supplied state and goals.
First correct a light mismatch. Then handle temperature with a 1 C deadband:
if hot, turn off a running heater first, otherwise enable cooling if off;
if cold, turn off running cooling first, otherwise enable heating if off;
within the deadband, turn off running heating or cooling. If nothing needs
changing call hold. Do not repeat commands that already match device state.
Use only the provided tool names and arguments. Never invent an entity.
"""

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
    def __init__(self, model="qwen3:0.6b", url="http://127.0.0.1:11434", timeout=120):
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout

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
                "think": False, "stream": False}

    def propose(self, state, seed=0):
        prompt = json.dumps(state, sort_keys=True, ensure_ascii=False)
        payload = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt}], "tools": TOOLS,
            "think": False, "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 256, "num_gpu": 0, "seed": seed}}
        start = time.perf_counter()
        raw = self.request("/api/chat", payload)
        return {"raw": raw, "prompt": payload["messages"], "options": payload["options"],
                "latency_ms": (time.perf_counter() - start) * 1000}
