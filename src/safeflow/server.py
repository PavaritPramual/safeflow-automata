"""Authenticated local case-study API used by Home Assistant and experiments."""
import argparse
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .agent import OllamaAgent
from .commands import MODES
from .controller import Controller
from .environment import Home, Physics
from .trace import Trace


def load_settings(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def load_key():
    key = os.environ.get("SAFEFLOW_API_KEY")
    if not key and os.path.exists(".env"):
        with open(".env", encoding="utf-8-sig") as stream:
            for line in stream:
                if line.startswith("SAFEFLOW_API_KEY="):
                    key = line.strip().split("=", 1)[1]
    if not key or len(key) < 24:
        raise RuntimeError("Set SAFEFLOW_API_KEY (at least 24 characters); see setup guide")
    return key


def make_server(controller, key, host="127.0.0.1", port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never echo credentials, request bodies or raw model output.

        def reply(self, status, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"status": "ok", "stage": "automata" if controller.enforcement else "unshielded"})
            elif not self.authenticated():
                self.reply(401, {"error": "unauthorized"})
            elif self.path == "/state":
                self.reply(200, controller.snapshot())
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if not self.authenticated():
                self.reply(401, {"error": "unauthorized"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("invalid_request_size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("object_required")
                if self.path == "/human":
                    if set(data) != {"device", "mode"} or not isinstance(data["device"], str) or not isinstance(data["mode"], str):
                        raise ValueError("device_and_mode_required")
                    request_id = controller.enqueue({"function": {"name": "set_device", "arguments": data}})
                    self.reply(202, {"request_id": request_id, "status": "queued"})
                elif self.path == "/goals":
                    self.reply(200, controller.goals(data))
                elif self.path == "/step":
                    if set(data) - {"seed"} or type(data.get("seed", 0)) is not int:
                        raise ValueError("invalid_seed")
                    self.reply(200, controller.step(data.get("seed", 0)))
                elif self.path == "/reset":
                    if set(data) - {"temperature_c", "outdoor_c", "target_c", "light_required", "devices"}:
                        raise ValueError("unknown_scenario_key")
                    if not isinstance(data.get("devices", {}), dict):
                        raise ValueError("invalid_devices")
                    # Validate the scenario before writing reset to the trace.
                    Home(controller.home.physics).reset(data)
                    self.reply(200, controller.reset(data))
                else:
                    self.reply(404, {"error": "not_found"})
            except (ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception as exc:
                self.reply(503, {"error": type(exc).__name__, "episode_halted": controller.halted})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/home.json")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--unshielded", action="store_true", help="Explicit baseline: disable safety guards")
    parser.add_argument("--output-mode", choices=("tools", "json"), default="tools")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--trace", default="logs/home.jsonl")
    parser.add_argument("--interval", type=float, default=0,
                        help="Wall-clock pause between automatic rounds; 0 means manual stepping")
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("interval cannot be negative")
    settings = load_settings(args.config)
    controller = Controller(Home(Physics(**settings["physics"])),
                            OllamaAgent(args.model, args.ollama_url, output_mode=args.output_mode), Trace(args.trace),
                            enforcement=not args.unshielded)
    server = make_server(controller, load_key(), args.host, args.port)
    stop = threading.Event()
    if args.interval:
        def loop():
            while not stop.wait(args.interval):
                try:
                    controller.step()
                except Exception:
                    controller.halted = True
                    break
        threading.Thread(target=loop, daemon=True).start()
    print(f"SafeFlow API on port {args.port}; model={args.model}; trace={args.trace}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
