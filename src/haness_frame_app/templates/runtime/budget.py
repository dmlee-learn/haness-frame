from __future__ import annotations

import time


class BudgetExceeded(RuntimeError):
    pass


class RunBudget:
    def __init__(
        self,
        *,
        max_elapsed_seconds: int,
        max_ai_calls: int,
        initial_elapsed_seconds: float = 0.0,
        initial_ai_calls: int = 0,
    ) -> None:
        self.max_elapsed_seconds = max_elapsed_seconds
        self.max_ai_calls = max_ai_calls
        self.started = time.monotonic() - max(0.0, initial_elapsed_seconds)
        self.ai_calls = max(0, initial_ai_calls)

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    def check(self, stage: str) -> None:
        if self.elapsed_seconds() >= self.max_elapsed_seconds:
            raise BudgetExceeded(f"elapsed-time budget exhausted before {stage}")

    def reserve_ai_call(self, role: str) -> None:
        self.check(f"{role} AI call")
        if self.ai_calls >= self.max_ai_calls:
            raise BudgetExceeded(f"AI-call budget exhausted before role: {role}")
        self.ai_calls += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
            "max_ai_calls": self.max_ai_calls,
            "ai_calls": self.ai_calls,
        }
