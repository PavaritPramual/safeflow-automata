"""Single writer: human requests and AI proposals share one logged path."""
import threading
import uuid
from collections import deque
from dataclasses import asdict
from .commands import decode_response
from .automata import Automata, POLICY_VERSION
import time


class Controller:
    def __init__(self, home, agent, trace, enforcement=True):
        self.home, self.agent, self.trace = home, agent, trace
        self.enforcement = enforcement
        self.automata = Automata()
        self.lock = threading.RLock()
        self.queue = deque()
        self.run_id = str(uuid.uuid4())
        self.halted = False
        self.metadata = agent.metadata()
        self.reset()

    def log(self, event, **fields):
        try:
            self.trace.write({"event": event, "run_id": self.run_id,
                              "episode_id": self.episode_id, **fields})
        except Exception:
            self.halted = True
            raise

    def reset(self, scenario=None):
        with self.lock:
            from .environment import Home
            # Reject a bad reset before changing state or writing an episode record.
            Home(self.home.physics).reset(scenario)
            self.episode_id = str(uuid.uuid4())
            self.log("reset", scenario=scenario or {}, model=self.metadata,
                     physics=asdict(self.home.physics), schema_version=2,
                     enforcement=self.enforcement, policy_version=POLICY_VERSION)
            self.home.reset(scenario)
            self.automata.reset(self.home.snapshot())
            self.queue.clear()
            self.halted = False
            self.last_result = None
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            return {**self.home.snapshot(), "run_id": self.run_id,
                    "episode_id": self.episode_id, "pending_requests": len(self.queue),
                    "halted": self.halted, "last_result": self.last_result,
                    "model": self.metadata, "enforcement": "automata" if self.enforcement else "validation_only",
                    "automata": self.automata.state, "policy_version": POLICY_VERSION}

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
            if old != self.automata.expected:
                self.halted = True
                raise ValueError("automata_state_mismatch")
            from .environment import Home
            validator = Home(self.home.physics)
            validator.reset({**old, "devices": old["devices"]})
            validator.set_goals(**values)
            self.log("goals", goals=values)
            self.home.set_goals(**values)
            self.automata.expected = self.home.snapshot()
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
                    command = decode_response(result["raw"], result.get("output_mode", "tools"))
                except ValueError as exc:
                    error = str(exc)
            proposal_id = str(uuid.uuid4())
            try:
                self.log("proposal", proposal_id=proposal_id, request_id=request_id, source=source,
                         before=before, model=self.metadata, seed=seed, **result,
                         validation="valid" if command else "invalid", reason=error,
                         command=command.to_dict() if command else None)
                started = time.perf_counter()
                checked = self.automata.evaluate(command, source, before)
                outcome = checked.outcome if self.enforcement or not command else "execute_unshielded"
                decision_reason = error or (checked.reason if self.enforcement else None)
                executed = command if outcome in ("allow", "human_bypass", "execute_unshielded") else None
                self.log("decision", proposal_id=proposal_id, source=source,
                         decision=outcome, reason=decision_reason, policy_version=POLICY_VERSION,
                         automata_before=self.automata.state, check_ms=(time.perf_counter()-started)*1000,
                         command=executed.to_dict() if executed else None)
            except Exception:
                self.halted = True
                raise
            if source == "human":
                self.queue.popleft()
            try:
                if executed:
                    self.home.apply(executed)
                after = self.home.advance(30)
                self.automata.observe(before, executed, after, 30)
                self.log("execution", proposal_id=proposal_id, source=source,
                         command=executed.to_dict() if executed else None, advance_s=30, after=after,
                         automata_after=self.automata.state)
            except Exception as exc:
                self.halted = True
                try:
                    self.log("fault", proposal_id=proposal_id, reason=type(exc).__name__,
                             message=str(exc), execution_may_have_occurred=True)
                except Exception:
                    pass  # A broken logger cannot record its own failure.
                raise
            self.last_result = {"proposal_id": proposal_id, "source": source,
                                "command": command.to_dict() if command else None,
                                "validation": "valid" if command else "invalid", "reason": decision_reason,
                                "decision": outcome, "executed_command": executed.to_dict() if executed else None}
            return self.snapshot()
