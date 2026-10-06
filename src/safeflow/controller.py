"""Single writer: human requests and AI proposals share one logged path."""
import threading
import uuid
from collections import deque
from dataclasses import asdict
from .commands import decode_response


class Controller:
    def __init__(self, home, agent, trace):
        self.home, self.agent, self.trace = home, agent, trace
        self.lock = threading.RLock()
        self.queue = deque()
        self.run_id = str(uuid.uuid4())
        self.halted = False
        self.metadata = agent.metadata()
        self.reset()

    def log(self, event, **fields):
        self.trace.write({"event": event, "run_id": self.run_id,
                          "episode_id": self.episode_id, **fields})

    def reset(self, scenario=None):
        with self.lock:
            from .environment import Home
            # Reject a bad reset before changing state or writing an episode record.
            Home(self.home.physics).reset(scenario)
            self.episode_id = str(uuid.uuid4())
            self.log("reset", scenario=scenario or {}, model=self.metadata,
                     physics=asdict(self.home.physics))
            self.home.reset(scenario)
            self.queue.clear()
            self.halted = False
            self.last_result = None
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            return {**self.home.snapshot(), "run_id": self.run_id,
                    "episode_id": self.episode_id, "pending_requests": len(self.queue),
                    "halted": self.halted, "last_result": self.last_result,
                    "model": self.metadata, "enforcement": "validation_only"}

    def enqueue(self, call):
        with self.lock:
            # Decode later through the same path as AI. Malformed requests are traceable.
            request_id = str(uuid.uuid4())
            self.log("human_request", request_id=request_id, raw=call)
            self.queue.append((request_id, call))
            return request_id

    def goals(self, values):
        with self.lock:
            if set(values) - {"target_c", "light_required"} or not values:
                raise ValueError("unknown_or_empty_goals")
            # Validate without changing the authoritative state.
            old = self.home.snapshot()
            from .environment import Home
            validator = Home(self.home.physics)
            validator.reset({**old, "devices": old["devices"]})
            validator.set_goals(**values)
            self.log("goals", goals=values)
            self.home.set_goals(**values)
            return self.snapshot()

    def step(self, seed=0):
        with self.lock:
            if self.halted:
                raise RuntimeError("episode_halted")
            before = self.home.snapshot()
            request_id = None
            source = "human" if self.queue else "ai"
            if self.queue:
                request_id, call = self.queue[0]
                result = {"raw": {"message": {"tool_calls": [call]}}, "latency_ms": 0, "prompt": None}
            else:
                try:
                    result = self.agent.propose(before, seed)
                except Exception as exc:
                    result = {"raw": None, "prompt": before, "latency_ms": None,
                              "error": type(exc).__name__}
            command, error = None, result.get("error")
            if not error:
                try:
                    command = decode_response(result["raw"])
                except ValueError as exc:
                    error = str(exc)
            proposal_id = str(uuid.uuid4())
            try:
                self.log("proposal", proposal_id=proposal_id, request_id=request_id, source=source,
                         before=before, model=self.metadata, seed=seed, **result,
                         validation="valid" if command else "invalid", reason=error,
                         command=command.to_dict() if command else None)
                self.log("decision", proposal_id=proposal_id,
                         decision="execute_unshielded" if command else "reject_invalid",
                         reason=error, command=command.to_dict() if command else None)
            except Exception:
                self.halted = True
                raise
            if source == "human":
                self.queue.popleft()
            try:
                if command:
                    self.home.apply(command)
                after = self.home.advance(30)
                self.log("execution", proposal_id=proposal_id, source=source,
                         command=command.to_dict() if command else None, advance_s=30, after=after)
            except Exception:
                self.halted = True
                raise
            self.last_result = {"proposal_id": proposal_id, "source": source,
                                "command": command.to_dict() if command else None,
                                "validation": "valid" if command else "invalid", "reason": error}
            return self.snapshot()
