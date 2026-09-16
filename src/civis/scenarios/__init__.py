"""
Scenario-level declarative extensions.

Historically the scenario YAML only carried the persona profile and the
list of expected agent actions (both consumed by the orchestrator and
the judge). Phase D+++ adds a second declarative surface — the
`available_actions` block — which the web UI reads to render clickable
attendant buttons ("verify identity", "issue certificate", ...).

Keeping this in its own package lets us grow the declarative surface
(future: available_forms, escalation_options) without bloating
`session.scenario`.
"""

from civis.scenarios.actions import AgentAction, AgentActionCatalog

__all__ = ["AgentAction", "AgentActionCatalog"]
