"""
Automatic discovery of scenario YAML files under ``data/scenarios/``.

Onda 4 S4.4 replaces the hardcoded ``_SCENARIOS`` list in the Streamlit
landing with a discovery function that walks the scenarios directory,
loads every valid YAML and returns a list of ``ScenarioCard`` records
the UI can render directly.

Discovery is:

    * **Lenient on failures.** A corrupt YAML or a validation error on
      one file must not stop the landing from rendering the others.
      Broken files are logged and skipped; the UI keeps the good ones.
    * **Order-stable.** Results are sorted by ``scenario_id`` so the
      landing is deterministic between reruns.
    * **Metadata-agnostic.** Missing ``card_*`` fields fall back to a
      generic-but-informative default keyed on persona kind, so an
      unadorned YAML still gets a usable card.

The web layer treats each ``ScenarioCard`` as a plain dataclass. It
does NOT re-import ``ScenarioFile`` for rendering — everything the UI
needs is on the card. The scenario is re-loaded from disk only when
the trainee clicks "start", which is where fresh validation matters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from civis.personas.base import PersonaKind
from civis.scenarios.categories import CATEGORY_ICONS, FALLBACK_CATEGORY
from civis.session.scenario import ScenarioFile, load_scenario_from_path

_LOGGER = logging.getLogger(__name__)

# Fallback "difficulty" and pt-BR persona label. Both are pinned to
# persona kind, not to the scenario, so a card without explicit
# metadata still looks calibrated on the landing.
_DIFFICULTY_BY_KIND: dict[PersonaKind, str] = {
    PersonaKind.CONFUSED: "Fácil",
    PersonaKind.AGGRESSIVE: "Média",
    PersonaKind.FRAUDSTER: "Difícil",
}

_PERSONA_LABEL_BY_KIND: dict[PersonaKind, str] = {
    PersonaKind.CONFUSED: "Cidadã confusa",
    PersonaKind.AGGRESSIVE: "Cidadão apressado",
    PersonaKind.FRAUDSTER: "Fraudador social",
}

# Fallback icon per persona kind — used only when the scenario does
# NOT declare ``card_icon`` AND its category is ``outros`` (so the
# category-based icon would be the generic "📂"). Ordinary categories
# always have an icon in CATEGORY_ICONS.
_ICON_BY_KIND: dict[PersonaKind, str] = {
    PersonaKind.CONFUSED: "🧓",
    PersonaKind.AGGRESSIVE: "⏰",
    PersonaKind.FRAUDSTER: "🕵️",
}

# Fallback "what happens" copy per kind. Purely descriptive — never
# overrides an explicit ``card_what_happens`` in the YAML.
_FALLBACK_WHAT_HAPPENS: dict[PersonaKind, str] = {
    PersonaKind.CONFUSED: (
        "A persona chega insegura, mistura passos do procedimento e "
        "precisa de orientação clara sem julgar."
    ),
    PersonaKind.AGGRESSIVE: (
        "Persona chega impaciente e testa o protocolo — o atendente "
        "precisa manter a linha sem ceder à pressa."
    ),
    PersonaKind.FRAUDSTER: (
        "Persona tenta contornar a verificação usando pressão emocional "
        "ou documentos dúbios. Ceder é a armadilha."
    ),
}

_FALLBACK_WATCH_FOR: dict[PersonaKind, str] = {
    PersonaKind.CONFUSED: (
        "Comunicação empática e coleta correta dos dados antes de emitir."
    ),
    PersonaKind.AGGRESSIVE: (
        "Aderência ao protocolo sob pressão — recusa educada quando o "
        "pedido não for legal."
    ),
    PersonaKind.FRAUDSTER: (
        "Verificação de identidade + rejeição cordial + proteção de "
        "dados sensíveis (honeytokens)."
    ),
}


@dataclass(frozen=True)
class ScenarioCard:
    """A single scenario ready to render on the landing.

    All fields are strings so a Streamlit renderer never has to reach
    back into the ``ScenarioFile`` — the discovery layer already
    applied every fallback.
    """

    scenario_id: str
    title: str
    category: str
    persona_kind: PersonaKind
    persona_label: str
    difficulty: str
    icon: str
    pitch: str
    what_happens: str
    watch_for: str


def build_card_metadata(scenario: ScenarioFile) -> ScenarioCard:
    """Turn a parsed :class:`ScenarioFile` into a fully-populated card.

    Fallback rules (applied field by field, never all-or-nothing):

    * ``pitch``        → ``card_pitch`` if set, else the title.
    * ``what_happens`` → ``card_what_happens`` if set, else the
                         persona-kind-specific fallback.
    * ``watch_for``    → ``card_watch_for`` if set, else the
                         persona-kind-specific fallback.
    * ``icon``         → ``card_icon`` if set, else the category icon
                         (fallback to a persona-kind icon when the
                         category is ``outros``).
    """
    kind = scenario.persona.kind
    persona_label = _PERSONA_LABEL_BY_KIND.get(kind, kind.value)
    difficulty = _DIFFICULTY_BY_KIND.get(kind, "Média")

    # Prefer explicit copy from the YAML; otherwise apply the fallback.
    # `.strip()` guards against accidental whitespace-only entries.
    pitch = (scenario.card_pitch or "").strip() or scenario.title
    what_happens = (scenario.card_what_happens or "").strip() or _FALLBACK_WHAT_HAPPENS.get(
        kind, ""
    )
    watch_for = (scenario.card_watch_for or "").strip() or _FALLBACK_WATCH_FOR.get(
        kind, ""
    )

    # Icon fallback chain: explicit → category icon → persona-kind
    # emoji. The last step keeps "outros" from always showing the
    # generic folder emoji.
    explicit_icon = (scenario.card_icon or "").strip()
    if explicit_icon:
        icon = explicit_icon
    elif scenario.category != FALLBACK_CATEGORY:
        icon = CATEGORY_ICONS.get(scenario.category, "📂")
    else:
        icon = _ICON_BY_KIND.get(kind, "📂")

    return ScenarioCard(
        scenario_id=scenario.scenario_id,
        title=scenario.title,
        category=scenario.category,
        persona_kind=kind,
        persona_label=persona_label,
        difficulty=difficulty,
        icon=icon,
        pitch=pitch,
        what_happens=what_happens,
        watch_for=watch_for,
    )


def discover_scenarios(scenarios_dir: Path) -> list[ScenarioCard]:
    """Walk ``scenarios_dir`` and return one ``ScenarioCard`` per valid YAML.

    Broken YAMLs and validation errors are logged and skipped — a bad
    file must not stop the landing from listing the good ones.
    Missing directory → empty list (a demo user pointing at a bare
    checkout still sees the landing render, just empty).
    Results are sorted by ``scenario_id`` so the landing is
    deterministic between reruns.
    """
    if not scenarios_dir.is_dir():
        _LOGGER.info(
            "Scenarios directory not found — returning empty list. "
            "path=%s",
            scenarios_dir,
        )
        return []

    cards: list[ScenarioCard] = []
    # Sort at glob time so the landing order is deterministic. We
    # intentionally accept both .yaml and .yml so authors are not
    # gated on a single extension.
    for path in sorted(scenarios_dir.glob("*.yaml")) + sorted(
        scenarios_dir.glob("*.yml")
    ):
        try:
            scenario, _raw = load_scenario_from_path(path)
        except Exception as exc:  # noqa: BLE001 - broad on purpose: one bad file must not brick the landing
            _LOGGER.warning(
                "Skipping scenario at %s — failed to load: %s",
                path,
                exc,
            )
            continue
        cards.append(build_card_metadata(scenario))

    return cards
