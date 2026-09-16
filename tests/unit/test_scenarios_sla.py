"""
Tests for the Onda 2 T1.1 ServiceSLA scenario extension.

Covers four concerns:

    - Parsing shape: ``ServiceSLA`` accepts the flat YAML mapping the
      task text specifies.
    - Defaults: a scenario without a ``service_sla`` block still loads
      and exposes the shared 480 / 720 / 900 numbers.
    - Ordering: target < warning < critical is enforced at load time
      with a clear error message.
    - Phase mapping: elapsed time crosses green → amber → warning → red
      exactly on the declared thresholds.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from civis.scenarios.sla import (
    DEFAULT_CRITICAL_SECONDS,
    DEFAULT_TARGET_SECONDS,
    DEFAULT_WARNING_SECONDS,
    ServiceSLA,
)
from civis.session.scenario import load_scenario_from_text

# Minimal YAML fragment reused across every parsing test.
_BASE_PERSONA_YAML = """
scenario_id: "sla_test_v1"
title: "Cenário de teste — SLA"

persona:
  kind: "confused"
  name: "Fulana"
  background: |
    Cidadã fictícia.
  goal: |
    Obter um documento.
  initial_emotion: "anxious"
  facts:
    - key: "birth_date"
      value: "12 de março de 1954"
      is_secret: false

expected_agent_actions:
  - "Verificar identidade."
"""


# ---------------------------------------------------------------------------
# Parsing + defaults
# ---------------------------------------------------------------------------


def test_scenario_without_service_sla_uses_defaults() -> None:
    """A scenario missing the ``service_sla`` block keeps loading and
    exposes the shared defaults so the UI timer never renders blank."""
    scenario = load_scenario_from_text(_BASE_PERSONA_YAML)

    assert scenario.service_sla.target_seconds == DEFAULT_TARGET_SECONDS
    assert scenario.service_sla.warning_seconds == DEFAULT_WARNING_SECONDS
    assert scenario.service_sla.critical_seconds == DEFAULT_CRITICAL_SECONDS


def test_scenario_with_service_sla_parses_all_fields() -> None:
    """The flat ``target_seconds / warning_seconds / critical_seconds``
    layout described in the Onda 2 task loads as-is."""
    yaml_text = _BASE_PERSONA_YAML + """
service_sla:
  target_seconds: 300
  warning_seconds: 600
  critical_seconds: 900
"""
    scenario = load_scenario_from_text(yaml_text)

    assert scenario.service_sla.target_seconds == 300
    assert scenario.service_sla.warning_seconds == 600
    assert scenario.service_sla.critical_seconds == 900


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_service_sla_rejects_non_increasing_thresholds() -> None:
    """target must be < warning; warning must be < critical."""
    with pytest.raises(ValidationError, match="target_seconds must be strictly less"):
        ServiceSLA(target_seconds=500, warning_seconds=500, critical_seconds=900)

    with pytest.raises(ValidationError, match="warning_seconds must be strictly less"):
        ServiceSLA(target_seconds=100, warning_seconds=200, critical_seconds=200)


def test_service_sla_rejects_zero_or_negative_thresholds() -> None:
    """All three thresholds are strictly positive — a 0-second window
    makes no operational sense and would break the phase check."""
    with pytest.raises(ValidationError):
        ServiceSLA(target_seconds=0, warning_seconds=100, critical_seconds=200)


# ---------------------------------------------------------------------------
# Phase mapping
# ---------------------------------------------------------------------------


def test_phase_for_elapsed_maps_boundaries_correctly() -> None:
    """
    Boundaries are inclusive on the upper bound of each phase:

        elapsed <  target                → green
        target <= elapsed <  warning     → amber
        warning <= elapsed <  critical   → warning (orange)
        critical <= elapsed              → red
    """
    sla = ServiceSLA(target_seconds=480, warning_seconds=720, critical_seconds=900)

    assert sla.phase_for_elapsed(0) == "green"
    assert sla.phase_for_elapsed(479) == "green"

    assert sla.phase_for_elapsed(480) == "amber"
    assert sla.phase_for_elapsed(719) == "amber"

    assert sla.phase_for_elapsed(720) == "warning"
    assert sla.phase_for_elapsed(899) == "warning"

    assert sla.phase_for_elapsed(900) == "red"
    assert sla.phase_for_elapsed(3600) == "red"
