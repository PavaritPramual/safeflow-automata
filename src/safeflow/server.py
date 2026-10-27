"""Historical HTTP fixture and key loading; CLI redirects to the verified API."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .environment import Home


from .configuration import load_key


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
    """Keep the old module entry point, but always use the verified service.

    make_server/Controller below are retained for historical regression tests;
    the supported command line cannot start that ungated prototype.
    """
    import sys
    from .cli import main as entry
    raise SystemExit(entry(['serve', *sys.argv[1:]]))



if __name__ == "__main__":
    main()
