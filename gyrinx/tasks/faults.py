"""
Fault injection for the local task queue.

Pub/Sub is at-least-once, retries on failure, and can be slow — and the codebase
is full of idempotency reasoning that only ever runs in production. This module
lets the local worker *reproduce* those conditions so the hardening can actually
be exercised (in dev, and via the pytest driver in CI).

Two complementary mechanisms:

- ``FaultConfig`` — *probabilistic* chaos for the running dev server, configured
  from settings/env (each delivery may be delayed, may fail, may be duplicated,
  may be dropped). Great for "leave it on for an afternoon and see what breaks".
- The manual test driver (``gyrinx.tasks.testing``) — *scripted, deterministic*
  faults (``fail_next``, ``redeliver_last``, ``drop_next``) for assertions.

Both ultimately feed the same delivery machinery in ``gyrinx.tasks.worker``.
"""

import os
import random
import threading
import time
from dataclasses import dataclass


@dataclass
class FaultConfig:
    """Probabilistic fault knobs applied per delivery.

    All rates are in ``[0, 1]``. Defaults are all-zero (a no-op), so an
    unconfigured queue behaves normally.
    """

    duplicate_rate: float = 0.0  # chance a successful delivery is redelivered once
    failure_rate: float = 0.0  # chance a delivery fails (nack → retry with backoff)
    drop_rate: float = 0.0  # chance a delivery is silently lost (never runs)
    latency_seconds: float = 0.0  # fixed delay added before each delivery
    latency_jitter: float = 0.0  # extra uniform-random delay in [0, jitter)
    seed: int | None = None

    def __post_init__(self):
        # nosec B311 - fault scheduling, not security; deterministic seed wanted.
        self._rng = random.Random(self.seed)  # nosec B311
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.duplicate_rate,
                self.failure_rate,
                self.drop_rate,
                self.latency_seconds,
                self.latency_jitter,
            )
        )

    def _roll(self) -> float:
        # random.Random isn't thread-safe; the worker pool shares one config.
        with self._lock:
            return self._rng.random()

    def should_duplicate(self) -> bool:
        return self.duplicate_rate > 0 and self._roll() < self.duplicate_rate

    def should_fail(self) -> bool:
        return self.failure_rate > 0 and self._roll() < self.failure_rate

    def should_drop(self) -> bool:
        return self.drop_rate > 0 and self._roll() < self.drop_rate

    def sleep(self) -> None:
        if self.latency_seconds <= 0 and self.latency_jitter <= 0:
            return
        delay = self.latency_seconds
        if self.latency_jitter > 0:
            delay += self._roll() * self.latency_jitter
        if delay > 0:
            time.sleep(delay)

    @classmethod
    def disabled(cls) -> FaultConfig:
        return cls()

    @classmethod
    def from_options(cls, options: dict | None) -> FaultConfig:
        """Build from a backend ``OPTIONS["faults"]`` dict (unknown keys ignored)."""
        if not options:
            return cls.disabled()
        allowed = {
            "duplicate_rate",
            "failure_rate",
            "drop_rate",
            "latency_seconds",
            "latency_jitter",
            "seed",
        }
        return cls(**{k: v for k, v in options.items() if k in allowed})

    @classmethod
    def from_env(cls, prefix: str = "TASKS_FAULT_") -> FaultConfig:
        """Build from environment variables, e.g. ``TASKS_FAULT_DUPLICATE_RATE=0.1``.

        Lets you flip chaos on for a dev-server session without editing settings.
        """

        def _f(name: str, default: float = 0.0) -> float:
            raw = os.getenv(prefix + name)
            if raw is None or raw == "":
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        seed_raw = os.getenv(prefix + "SEED")
        seed = int(seed_raw) if seed_raw not in (None, "") else None

        return cls(
            duplicate_rate=_f("DUPLICATE_RATE"),
            failure_rate=_f("FAILURE_RATE"),
            drop_rate=_f("DROP_RATE"),
            latency_seconds=_f("LATENCY_SECONDS"),
            latency_jitter=_f("LATENCY_JITTER"),
            seed=seed,
        )
