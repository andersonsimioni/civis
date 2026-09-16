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

Keeping this in its own package lets us grow the declarative surface
(future: available_forms, escalation_options) without bloating
`session.scenario`.
"""

from civis.scenarios.actions import AgentAction, AgentActionCatalog
from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.scenarios.sla import ServiceSLA

__all__ = [
    "AgentAction",
    "AgentActionCatalog",
    "HiddenAgenda",
    "ServiceSLA",
    "SuccessCriterion",
]
