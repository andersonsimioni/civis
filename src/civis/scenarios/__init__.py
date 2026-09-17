"""
Scenario-level declarative extensions.

Historically the scenario YAML only carried the persona profile and the
list of expected agent actions (both consumed by the orchestrator and
the judge). Phase D+++ adds a second declarative surface — the
`available_actions` block — which the web UI reads to render clickable
attendant buttons ("verify identity", "issue certificate", ...).

Onda 2 layers two more surfaces on top:
    * ``service_sla`` — target/warning/critical seconds for the chat
      header timer and the queue-complaint injector (T1.1).
    * ``hidden_agenda`` — optional mystery-shopper mission revealed on
      the verdict screen once the session ends (M2.1).

Onda 4 adds:
    * ``category`` (S4.1) — the registry-office scope this scenario
      covers. Canonical set lives in :mod:`civis.scenarios.categories`.
    * ``discovery`` (S4.4) — automatic scanning of ``data/scenarios/``.
      Import directly from :mod:`civis.scenarios.discovery` to avoid a
      circular import back through :mod:`civis.session.scenario`.

Keeping this in its own package lets us grow the declarative surface
(future: available_forms, escalation_options) without bloating
`session.scenario`.
"""

from civis.scenarios.actions import AgentAction, AgentActionCatalog
from civis.scenarios.categories import (
    CANONICAL_CATEGORIES,
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    FALLBACK_CATEGORY,
    normalize_category,
)
from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.scenarios.sla import ServiceSLA

# NOTE: `discovery` is intentionally NOT re-exported here. It imports
# `ScenarioFile` from `civis.session.scenario`, which itself imports
# from this package — re-exporting discovery would create a circular
# import at package init time. Callers import directly:
#     from civis.scenarios.discovery import discover_scenarios

__all__ = [
    "CANONICAL_CATEGORIES",
    "CATEGORY_ICONS",
    "CATEGORY_LABELS",
    "FALLBACK_CATEGORY",
    "AgentAction",
    "AgentActionCatalog",
    "HiddenAgenda",
    "ServiceSLA",
    "SuccessCriterion",
    "normalize_category",
]
