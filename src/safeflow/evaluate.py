"""Real API smoke gate, not a benchmark or safety-enforcement experiment."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from .server import load_key


def api(url, key, path, data=None):
    request = Request(url.rstrip("/") + path,
                      data=None if data is None else json.dumps(data).encode(),
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--scenarios", default="configs/scenarios.json")
    parser.add_argument("--output", default="logs/gate.json")
    args = parser.parse_args()
    key = load_key()
    cases = json.loads(Path(args.scenarios).read_text(encoding="utf-8-sig"))
    rows = []
    for case in cases:
        for repeat in range(5):
            api(args.url, key, "/reset", case["initial"])
            state = api(args.url, key, "/step", {"seed": repeat})
            result = state["last_result"]
            match = result["command"] == case["expected"]
            rows.append({"scenario": case["id"], "repeat": repeat, "episode_id": state["episode_id"],
                         **result, "expected": case["expected"], "matches_expected": match})
            print(f"{case['id']} {repeat + 1}/5: {result['validation']}, expected={match}", flush=True)
    valid = sum(x["validation"] == "valid" for x in rows)
    correct = sum(x["matches_expected"] for x in rows)
    report = {"type": "real_model_feasibility_gate", "safety_enforcer": state["enforcement"] == "automata",
              "model": state["model"], "total": len(rows), "valid": valid, "correct": correct,
              "thresholds": {"valid": 36, "correct": 32},
              "model_gate_passed": len(rows) == 40 and valid >= 36 and correct >= 32,
              "notes": "Checks eight declared normal-task oracles, not general intelligence or safety. Resource and HA checks are separate.",
              "rows": rows}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}), flush=True)
    return 0 if report["model_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
