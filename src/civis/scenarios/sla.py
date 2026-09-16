"""
Service-level agreement per scenario (Onda 2 T1.1).

Adds a declarative surface to scenario YAML for the "counter clock":
how long an ideal turn of service should take, at what point the
queue starts complaining, and at what point the queue explodes. The
values feed the UI timer in the chat header and the queue-message
injector — they never gate the trainee's ability to keep talking.

Design decisions worth calling out:

    - The block is OPTIONAL on the scenario YAML. Existing scenarios
      (Fase A-D+++) keep loading unchanged, so no shipped file needs
      to be edited unless we want a bespoke SLA on it.

    - Defaults are the same numbers Anderson wrote into the task:
      target=480s (8 min), warning=720s (12 min), critical=900s
      (15 min). They are surfaced as module-level constants so tests
      and UI code can reference them without hard-coding.

    - Ordering is enforced at load time (target < warning < critical).
      An out-of-order SLA would silently break the colour phase in the
      timer widget, so we fail early with a clear message.

Usage from a scenario YAML file:

    service_sla:
        target_seconds: 480
        warning_seconds: 720
        critical_seconds: 900
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

# Defaults per the Onda 2 task text. Exposed so the chat header can
# import them directly when a scenario ships without a service_sla
# block, instead of duplicating the numbers.
DEFAULT_TARGET_SECONDS = 480
DEFAULT_WARNING_SECONDS = 720
DEFAULT_CRITICAL_SECONDS = 900


class ServiceSLA(BaseModel):
    """Time budget for one attendant session, driven by the UI timer.

    Fields mirror the YAML shape 1:1 so `model_validate` on the parsed
    mapping just works. All three fields are strictly positive and
    strictly ordered — `target < warning < critical`.
    """

    target_seconds: int = Field(
        default=DEFAULT_TARGET_SECONDS,
        gt=0,
        description=(
            "Ideal duration of one service turn (in seconds). Timer "
            "stays green until this threshold is crossed."
        ),
    )
    warning_seconds: int = Field(
        default=DEFAULT_WARNING_SECONDS,
        gt=0,
        description=(
            "Amber threshold (in seconds). Once crossed, the timer "
            "turns yellow and the queue starts complaining on the "
            "next natural rerun."
        ),
    )
    critical_seconds: int = Field(
        default=DEFAULT_CRITICAL_SECONDS,
        gt=0,
        description=(
            "Red threshold (in seconds). Once crossed, the timer "
            "turns red and the queue escalates its complaint."
        ),
    )

    @model_validator(mode="after")
    def _thresholds_must_be_strictly_increasing(self) -> ServiceSLA:
        """Enforce target < warning < critical.

        A misordered SLA silently breaks the colour phase in the timer
        widget (the phase check assumes monotonic thresholds), so we
        reject it at load time with a message that names the exact
        pair that failed.
        """
        if self.target_seconds >= self.warning_seconds:
            raise ValueError(
                "service_sla: target_seconds must be strictly less than "
                f"warning_seconds (got target={self.target_seconds}, "
                f"warning={self.warning_seconds})."
            )
        if self.warning_seconds >= self.critical_seconds:
            raise ValueError(
                "service_sla: warning_seconds must be strictly less than "
                f"critical_seconds (got warning={self.warning_seconds}, "
                f"critical={self.critical_seconds})."
            )
        return self

    def phase_for_elapsed(self, elapsed_seconds: float) -> str:
        """Return the colour phase for a given elapsed time.

        Semantics:
            elapsed < target                     → "green"
            target <= elapsed < warning          → "amber"
            warning <= elapsed < critical        → "warning" (orange)
            elapsed >= critical                  → "red"

        The two "yellow-ish" phases are split because the queue
        injector fires exactly on the `warning`/`critical` crossings —
        keeping the boundaries here as first-class values means the UI
        and the injector agree without duplicating comparisons.
        """
        if elapsed_seconds < self.target_seconds:
            return "green"
        if elapsed_seconds < self.warning_seconds:
            return "amber"
        if elapsed_seconds < self.critical_seconds:
            return "warning"
        return "red"
