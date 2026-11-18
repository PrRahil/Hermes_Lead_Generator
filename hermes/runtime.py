from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunnerStatus:
    mode: str = "idle"  # idle | continuous | one_shot
    running: bool = False
    started_at: Optional[str] = None
    last_cycle_at: Optional[str] = None
    cycle: int = 0
    current_query: str = ""
    last_signals: int = 0
    last_new_leads: int = 0
    total_new_leads: int = 0
    strong_leads_target: int = 50
    message: str = "Agent idle — start with: python -m hermes run"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status = RunnerStatus()

    def set_continuous_start(self, target: int = 50) -> None:
        with self._lock:
            self.status = RunnerStatus(
                mode="continuous",
                running=True,
                started_at=_utc(),
                strong_leads_target=target,
                message="Continuous lead hunt started",
            )

    def set_idle(self, message: str = "Stopped") -> None:
        with self._lock:
            self.status.running = False
            self.status.mode = "idle"
            self.status.message = message

    def tick(
        self,
        *,
        cycle: int,
        query: str,
        signals: int,
        new_leads: int,
        message: str = "",
    ) -> None:
        with self._lock:
            self.status.cycle = cycle
            self.status.current_query = query
            self.status.last_cycle_at = _utc()
            self.status.last_signals = signals
            self.status.last_new_leads = new_leads
            self.status.total_new_leads += new_leads
            if message:
                self.status.message = message

    def push_error(self, err: str) -> None:
        with self._lock:
            self.status.errors = (self.status.errors + [err])[-8:]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self.status.to_dict()


BUS = RuntimeBus()
