"""Exercise the actual Home Assistant API against the owned localhost lab.

--bootstrap-lab creates a random local test account only on a fresh lab.
Credentials are written to ignored logs/ha-credentials.json, never stdout.
"""
import argparse
import json
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from safeflow.evaluate import api
from safeflow.server import load_key

BASE = "http://127.0.0.1:8123"
CLIENT = BASE + "/"
CREDENTIALS = Path("logs/ha-credentials.json")


def request(path, data=None, token=None, form=False):
    body = None if data is None else (urlencode(data) if form else json.dumps(data)).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(BASE + path, data=body, headers=headers), timeout=180) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-lab", action="store_true")
    args = parser.parse_args()
    if CREDENTIALS.exists():
        stored = json.loads(CREDENTIALS.read_text())
        auth = request("/auth/token", {"grant_type": "refresh_token", "refresh_token": stored["refresh_token"],
                                       "client_id": CLIENT}, form=True)
    elif args.bootstrap_lab:
        steps = request("/api/onboarding")
        if any(x["step"] == "user" and x["done"] for x in steps):
            raise RuntimeError("Existing account: refusing to bootstrap or overwrite")
        stored = {"username": "safeflow-lab", "password": secrets.token_urlsafe(24)}
        code = request("/api/onboarding/users", {"name": "SafeFlow Lab", **stored,
                                                "client_id": CLIENT, "language": "en"})["auth_code"]
        auth = request("/auth/token", {"grant_type": "authorization_code", "code": code,
                                       "client_id": CLIENT}, form=True)
        stored["refresh_token"] = auth["refresh_token"]
        CREDENTIALS.write_text(json.dumps(stored), encoding="utf-8")
        for path, data in (("core_config", {}), ("analytics", {}),
                           ("integration", {"client_id": CLIENT, "redirect_uri": CLIENT})):
            request("/api/onboarding/" + path, data, auth["access_token"])
    else:
        raise RuntimeError("Run --bootstrap-lab once on the newly created lab container")
    token = auth["access_token"]
    states = {s["entity_id"]: s for s in request("/api/states", token=token)}
    required = ["sensor.safeflow_temperature", "sensor.safeflow_power", "sensor.safeflow_energy",
                "sensor.safeflow_simulation_time", "sensor.safeflow_pending", "sensor.safeflow_status",
                "number.safeflow_target_temperature", "switch.safeflow_light_required",
                "switch.safeflow_air_conditioner", "switch.safeflow_heater",
                "switch.safeflow_ventilation_fan", "switch.safeflow_light",
                "button.safeflow_step", "button.safeflow_reset"]
    assert all(s in states and states[s]["state"] != "unavailable" for s in required), "missing/unavailable HA entity"
    def service(domain, action, data):
        return request(f"/api/services/{domain}/{action}", data, token)
    service("button", "press", {"entity_id": "button.safeflow_reset"})
    service("number", "set_value", {"entity_id": "number.safeflow_target_temperature", "value": 24})
    service("switch", "turn_on", {"entity_id": "switch.safeflow_light_required"})
    service("switch", "turn_on", {"entity_id": "switch.safeflow_light"})
    key = load_key()
    before = api("http://127.0.0.1:8765", key, "/state")
    assert before["target_c"] == 24 and before["light_required"]
    assert before["pending_requests"] == 1 and before["devices"]["light"] == "off"
    service("button", "press", {"entity_id": "button.safeflow_step"})
    human = api("http://127.0.0.1:8765", key, "/state")
    assert human["last_result"]["source"] == "human" and human["devices"]["light"] == "on"
    service("button", "press", {"entity_id": "button.safeflow_step"})
    ai = api("http://127.0.0.1:8765", key, "/state")
    assert ai["last_result"]["source"] == "ai" and ai["simulation_time_s"] == 60
    report = {"type": "real_home_assistant_api_smoke", "entities": required,
              "queued_without_execution": True, "goal_update": True,
              "human_replaces_ai_one_round": True, "ai_resumes": True,
              "simulation_time_s": ai["simulation_time_s"], "safety_enforcer": False}
    Path("logs/ha-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
