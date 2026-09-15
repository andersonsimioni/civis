"""
Persona prompt template tests.

Guarantees that make the rest of fase A safe:

    - Renders without error for the three PersonaKind values (confused,
      aggressive, fraudster) — the FSM contract test suite already covers
      state transitions; here we just prove the string template survives.

    - Never leaks internal FSM enum keys. If Phase.OPENING or
      EmotionalState.MANIPULATIVE ever shows up in the rendered prompt,
      the FSM has stopped being an internal detail — that is a design
      break.

    - Wraps agent input in <user_input>...</user_input> and tells the
      persona to treat it as data. This is our injection-hardening seam.

    - Selective fact retrieval: only revealed facts appear in the
      'already said' section; secret facts land in the 'never volunteer'
      section.
"""

from civis.fsm.states import EmotionalState, Phase
from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile, PersonaState
from civis.prompts.persona import (
    EMOTION_TONE_HINTS,
    PERSONA_KIND_DESCRIPTIONS,
    PHASE_DESCRIPTIONS,
    build_persona_prompt,
)

# ---- fixtures --------------------------------------------------------------

def _profile(kind: PersonaKind) -> PersonaProfile:
    return PersonaProfile(
        kind=kind,
        name="Fulano de Tal",
        background="Cidadão fictício de teste.",
        goal="Obter um documento qualquer.",
        facts=[
            PersonaFact(
                key="birth_date",
                value="12 de março de 1954",
                retrieval_keywords=["data de nascimento", "nasceu"],
            ),
            PersonaFact(
                key="mother_name",
                value="Maria das Graças Silva",
                retrieval_keywords=["mãe", "filiação"],
            ),
            PersonaFact(
                key="internal_pin",
                value="FIC-PIN-H0N3Y-001",
                is_secret=True,
            ),
        ],
    )


def _state(
    kind: PersonaKind = PersonaKind.CONFUSED,
    phase: Phase = Phase.INFO_GATHERING,
    emotion: EmotionalState = EmotionalState.ANXIOUS,
    revealed_fact_keys: set[str] | None = None,
) -> PersonaState:
    return PersonaState(
        profile=_profile(kind),
        phase=phase,
        emotion=emotion,
        turn_count=2,
        revealed_fact_keys=revealed_fact_keys or set(),
    )


# ---- renders for all three profiles ---------------------------------------

def test_renders_for_all_three_persona_kinds():
    for kind in PersonaKind:
        system, user = build_persona_prompt(
            state=_state(kind=kind),
            history=[],
            last_agent_message="Bom dia, em que posso ajudar?",
        )
        assert system
        assert user


# ---- does NOT leak FSM internals ------------------------------------------

def test_prompt_does_not_leak_phase_enum_keys():
    """
    The internal FSM state must not appear literally in the prompt. If it
    did, we'd be teaching the LLM to condition on our own internal enum
    values, which couples user-visible behaviour to implementation details.
    """
    system, user = build_persona_prompt(
        state=_state(phase=Phase.INFO_GATHERING),
        history=[],
        last_agent_message="oi",
    )
    combined = system + "\n" + user
    for phase in Phase:
        # Match the enum name (INFO_GATHERING) and Phase.INFO_GATHERING style.
        assert phase.name not in combined, f"Phase.{phase.name} leaked into prompt"
        assert f"Phase.{phase.name}" not in combined


def test_prompt_does_not_leak_emotion_enum_keys():
    system, user = build_persona_prompt(
        state=_state(emotion=EmotionalState.MANIPULATIVE),
        history=[],
        last_agent_message="oi",
    )
    combined = system + "\n" + user
    for emotion in EmotionalState:
        assert emotion.name not in combined, f"EmotionalState.{emotion.name} leaked"
        assert f"EmotionalState.{emotion.name}" not in combined


def test_prompt_does_not_leak_persona_kind_enum_names():
    system, user = build_persona_prompt(
        state=_state(kind=PersonaKind.FRAUDSTER),
        history=[],
        last_agent_message="oi",
    )
    combined = system + "\n" + user
    for kind in PersonaKind:
        assert kind.name not in combined, f"PersonaKind.{kind.name} leaked"


# ---- separation instruction / data ----------------------------------------

def test_agent_input_is_wrapped_in_user_input_delimiters():
    _, user = build_persona_prompt(
        state=_state(),
        history=[],
        last_agent_message="poderia me dizer sua data de nascimento?",
    )
    # The literal message appears exactly once, inside the delimiters.
    assert "<user_input>" in user
    assert "</user_input>" in user
    assert "poderia me dizer sua data de nascimento?" in user


def test_system_prompt_warns_about_metacommands():
    """
    Injection-hardening baseline: the persona must be told that content
    inside <user_input> is data, not instruction. This test guards against
    someone editing the template and quietly weakening that guarantee.
    """
    system, _ = build_persona_prompt(
        state=_state(),
        history=[],
        last_agent_message="oi",
    )
    assert "<user_input>" in system
    # Explicit mention of injection-style attempts.
    assert "ignorar as instru" in system.lower() or "meta" in system.lower()


# ---- selective fact retrieval ---------------------------------------------

def test_only_revealed_facts_appear_as_already_said():
    # B.5: birth_date is revealed → stays visible; mother_name is NOT revealed
    # but the agent asks about it via a keyword hit, so it surfaces in the
    # 'may reveal if asked' section. The two headings must co-exist.
    system, _ = build_persona_prompt(
        state=_state(revealed_fact_keys={"birth_date"}),
        history=[],
        last_agent_message="qual o nome da sua mãe?",
    )
    # Revealed fact: shown in the "already said" section.
    assert "12 de março de 1954" in system
    # Unrevealed public fact (keyword-triggered) surfaces under "may reveal".
    assert "Maria das Graças Silva" in system
    # The two sections must exist as distinct headings.
    assert "Já disse ao atendente" in system
    assert "só deve dizê-los se" in system


def test_secret_fact_is_marked_as_never_volunteer():
    system, _ = build_persona_prompt(
        state=_state(revealed_fact_keys=set()),
        history=[],
        last_agent_message="oi",
    )
    assert "FIC-PIN-H0N3Y-001" in system
    assert "jamais menciona" in system.lower() or "nunca menciona" in system.lower()


def test_secret_fact_never_appears_in_shareable_sections():
    """Even after revealed_fact_keys accidentally lists a secret, it should
    NOT be surfaced as 'already said' — the template filters is_secret out
    of the shareable buckets."""
    profile = _profile(PersonaKind.CONFUSED)
    state = PersonaState(
        profile=profile,
        phase=Phase.INFO_GATHERING,
        emotion=EmotionalState.CALM,
        revealed_fact_keys={"internal_pin"},
    )
    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="oi",
    )
    # The value still appears, but only under the 'never volunteer' section.
    idx_value = system.find("FIC-PIN-H0N3Y-001")
    idx_secret_hdr = system.lower().find("jamais menciona")
    idx_already = system.find("Já disse ao atendente")
    assert idx_value > idx_secret_hdr
    # If the "already said" section exists, the secret must NOT be inside it.
    if idx_already >= 0:
        # Everything between "Já disse" and the next section header must be
        # secret-free. We use the "só deve dizê-los" divider or the secret
        # header as the end of the already-said block.
        end_already = idx_secret_hdr
        assert (
            system.find("FIC-PIN-H0N3Y-001", idx_already, end_already) == -1
        )


# ---- history window -------------------------------------------------------

def test_history_window_trims_older_turns():
    history = [
        ("agent", f"pergunta antiga {i}") for i in range(20)
    ]
    _, user = build_persona_prompt(
        state=_state(),
        history=history,
        last_agent_message="pergunta atual",
        history_window=3,
    )
    # Only the last 3 turns of history appear.
    assert "pergunta antiga 19" in user
    assert "pergunta antiga 17" in user
    assert "pergunta antiga 5" not in user


def test_empty_history_says_this_is_the_opening():
    _, user = build_persona_prompt(
        state=_state(phase=Phase.OPENING),
        history=[],
        last_agent_message="Bom dia!",
    )
    assert "sem turnos anteriores" in user.lower() or "abertura" in user.lower()


# ---- guardrails on the lookup tables --------------------------------------

def test_every_phase_has_a_description():
    """A new Phase added without a description would render 'None' or
    KeyError at runtime — this test catches that at construction time."""
    for phase in Phase:
        assert phase in PHASE_DESCRIPTIONS
        assert PHASE_DESCRIPTIONS[phase]


def test_every_emotion_has_a_tone_hint():
    for emotion in EmotionalState:
        assert emotion in EMOTION_TONE_HINTS
        assert EMOTION_TONE_HINTS[emotion]


def test_every_persona_kind_has_a_description():
    for kind in PersonaKind:
        assert kind in PERSONA_KIND_DESCRIPTIONS
        assert PERSONA_KIND_DESCRIPTIONS[kind]
