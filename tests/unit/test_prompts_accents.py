"""
Regional-accent prompt block tests (Onda-1 F1.2).

Two guarantees:

    1. When `PersonaProfile.regional_accent` is set, the system prompt
       carries a `# Sotaque` header followed by the exact steering
       paragraph declared in ACCENT_DESCRIPTIONS. One test per accent
       (7 accents = 7 tests) so a regression on any single one shows up
       cleanly.

    2. When `regional_accent` is None (the default), the system prompt
       is BYTE-IDENTICAL to the same profile without the field. That is
       the backwards-compat contract for shipping scenarios.
"""

import pytest

from civis.fsm.states import EmotionalState, Phase
from civis.personas.accents import RegionalAccent
from civis.personas.base import PersonaKind, PersonaProfile, PersonaState
from civis.prompts.accents import ACCENT_DESCRIPTIONS
from civis.prompts.persona import build_persona_prompt


def _make_state(accent: RegionalAccent | None) -> PersonaState:
    """Minimal PersonaState carrying the requested accent (or none)."""
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Fulano de Tal",
        background="Cidadão fictício de teste.",
        goal="Obter um documento qualquer.",
        regional_accent=accent,
    )
    return PersonaState(
        profile=profile,
        phase=Phase.INFO_GATHERING,
        emotion=EmotionalState.CALM,
    )


# ---- one test per accent: `# Sotaque` block appears and carries the right text.

@pytest.mark.parametrize("accent", list(RegionalAccent))
def test_accent_block_present_and_correct_per_region(accent: RegionalAccent):
    """
    Every RegionalAccent value renders the corresponding steering
    paragraph under a `# Sotaque` heading in the system prompt.
    """
    state = _make_state(accent=accent)

    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="oi, tudo bem?",
    )

    assert "# Sotaque" in system, (
        f"missing `# Sotaque` header for {accent.value}"
    )
    expected_text = ACCENT_DESCRIPTIONS[accent]
    assert expected_text in system, (
        f"steering paragraph for {accent.value} not found in prompt"
    )


# ---- retrocompat: no accent => no accent block, byte-identical output ------

def test_no_accent_produces_no_sotaque_block():
    """
    Absent accent must not introduce a `# Sotaque` block. The header string
    is unique enough that a substring check is safe.
    """
    state = _make_state(accent=None)

    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="bom dia",
    )

    assert "# Sotaque" not in system
    # None of the accent-specific interjections should leak in either.
    for marker in ("ôxente", "bah", "mano", "caraca", "uai", "égua"):
        assert marker not in system, (
            f"accent marker '{marker}' leaked into a neutral prompt"
        )


def test_prompt_byte_identical_without_accent_field():
    """
    Building the same profile with and without touching `regional_accent`
    must yield the exact same system prompt bytes. Guards the backwards-
    compat promise for pre-onda-1 shipping scenarios.
    """
    # Profile A: no accent field set at all (uses default None).
    profile_default = PersonaProfile(
        kind=PersonaKind.AGGRESSIVE,
        name="Roberto Almeida",
        background="Cidadão irritado.",
        goal="Obter documento agora.",
    )
    # Profile B: accent set explicitly to None (should render identically).
    profile_explicit_none = PersonaProfile(
        kind=PersonaKind.AGGRESSIVE,
        name="Roberto Almeida",
        background="Cidadão irritado.",
        goal="Obter documento agora.",
        regional_accent=None,
    )
    state_default = PersonaState(profile=profile_default)
    state_explicit = PersonaState(profile=profile_explicit_none)

    system_a, user_a = build_persona_prompt(
        state=state_default, history=[], last_agent_message="oi"
    )
    system_b, user_b = build_persona_prompt(
        state=state_explicit, history=[], last_agent_message="oi"
    )

    assert system_a == system_b
    assert user_a == user_b


def test_accent_block_appears_after_final_reminder():
    """
    The `# Sotaque` block is appended AFTER the injection-hardening
    sandwich (Papel + Regras de fala + Lembrete final). If it lands
    before the final reminder, an adversarial `last_agent_message`
    could sit closer to the model's attention than the anti-injection
    rules — that is the bug this test guards against.
    """
    state = _make_state(accent=RegionalAccent.NORDESTE)
    system, _ = build_persona_prompt(
        state=state, history=[], last_agent_message="oi"
    )
    idx_reminder = system.index("# Lembrete final")
    idx_accent = system.index("# Sotaque")
    assert idx_accent > idx_reminder, (
        "accent block must be appended after the final reminder"
    )
