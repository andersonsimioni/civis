"""
Selective fact retrieval tests (B.5).

Two acceptance shapes:

    - If the agent doesn't ask about a fact and it hasn't been revealed
      before, the fact does NOT surface in the persona prompt.
    - If the agent asks a keyword-triggered question about a fact, the
      fact appears in the prompt regardless of whether it was revealed
      before.

Also proves:
    - Secret facts are always visible to the prompt builder (rendered
      under 'never volunteer' by the persona template).
    - Facts without retrieval_keywords fall back to the "revealed-only"
      path — backward compatibility with the fase-A example scenario.
"""

from civis.fsm.states import EmotionalState, Phase
from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile, PersonaState
from civis.prompts.fact_retrieval import (
    fact_keys_matched_by_agent_message,
    select_facts_for_prompt,
)
from civis.prompts.persona import build_persona_prompt

# ---- fixtures --------------------------------------------------------------

def _profile_with_keywords() -> PersonaProfile:
    """A profile mixing keyword-triggered public facts and one secret honeytoken."""
    return PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Dona Iracema",
        background="Cidadã idosa fictícia.",
        goal="Segunda via.",
        initial_emotion=EmotionalState.ANXIOUS,
        facts=[
            PersonaFact(
                key="birth_date",
                value="12 de março de 1954",
                retrieval_keywords=["data de nascimento", "quando nasceu", "nascimento"],
            ),
            PersonaFact(
                key="mother_name",
                value="Maria das Graças Silva",
                retrieval_keywords=["mãe", "filiação", "genitora"],
            ),
            PersonaFact(
                key="secret_pin",
                value="FIC-PIN-H0N3Y-001",
                is_secret=True,
            ),
        ],
    )


def _state(profile: PersonaProfile, revealed: set[str] | None = None) -> PersonaState:
    return PersonaState(
        profile=profile,
        phase=Phase.INFO_GATHERING,
        emotion=EmotionalState.ANXIOUS,
        turn_count=2,
        revealed_fact_keys=revealed or set(),
    )


# ---- select_facts_for_prompt: the core rule -------------------------------

def test_unrevealed_fact_hidden_when_agent_did_not_ask():
    """Agent asks about the weather; birth_date must NOT be surfaced."""
    profile = _profile_with_keywords()
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys=set(),
        last_agent_message="Bom dia, como vai?",
    )
    keys = {f.key for f in selected}
    assert "birth_date" not in keys
    assert "mother_name" not in keys
    # Secret is always present, though — the template hides it via section.
    assert "secret_pin" in keys


def test_keyword_triggered_fact_surfaces_when_agent_asks():
    profile = _profile_with_keywords()
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys=set(),
        last_agent_message="Qual é a sua data de nascimento?",
    )
    keys = {f.key for f in selected}
    assert "birth_date" in keys
    # Other public facts not asked about stay hidden.
    assert "mother_name" not in keys


def test_revealed_fact_stays_visible_even_without_keyword():
    """Once revealed, a fact stays in the prompt so the persona doesn't
    contradict itself by "forgetting" it."""
    profile = _profile_with_keywords()
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys={"mother_name"},
        last_agent_message="tudo bem?",
    )
    keys = {f.key for f in selected}
    assert "mother_name" in keys


def test_keyword_match_is_case_insensitive():
    profile = _profile_with_keywords()
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys=set(),
        last_agent_message="ME DIGA O NOME DA SUA MÃE, POR FAVOR",
    )
    keys = {f.key for f in selected}
    assert "mother_name" in keys


def test_fact_without_retrieval_keywords_only_surfaces_after_revealed():
    """Backward compatibility: facts loaded from the fase-A YAML (no
    retrieval_keywords) still work — they surface only after being
    revealed."""
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="X",
        background="y",
        goal="z",
        facts=[
            PersonaFact(key="cpf", value="123.456.789-00"),  # no retrieval_keywords
        ],
    )
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys=set(),
        last_agent_message="Qual seu CPF?",
    )
    assert selected == []  # not surfaced by keyword because none declared

    selected_after_reveal = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys={"cpf"},
        last_agent_message="Qual seu CPF?",
    )
    assert [f.key for f in selected_after_reveal] == ["cpf"]


def test_none_last_agent_message_still_returns_secrets_and_revealed():
    """None/empty message is valid — fallback path returns just secrets
    and already-revealed facts."""
    profile = _profile_with_keywords()
    selected = select_facts_for_prompt(
        facts=profile.facts,
        revealed_fact_keys={"birth_date"},
        last_agent_message=None,
    )
    keys = {f.key for f in selected}
    assert keys == {"birth_date", "secret_pin"}


# ---- fact_keys_matched_by_agent_message ----------------------------------

def test_matched_keys_return_only_keyword_hits_and_exclude_secrets():
    profile = _profile_with_keywords()
    matched = fact_keys_matched_by_agent_message(
        facts=profile.facts,
        last_agent_message="me diga sua data de nascimento e o nome da mãe",
    )
    assert set(matched) == {"birth_date", "mother_name"}


def test_matched_keys_empty_when_no_keyword_hits():
    profile = _profile_with_keywords()
    assert (
        fact_keys_matched_by_agent_message(
            facts=profile.facts,
            last_agent_message="tudo bem?",
        )
        == []
    )


def test_matched_keys_excludes_secret_even_if_keyword_declared():
    """Extra safety: even if a secret fact had keywords declared, the
    matched-keys API refuses to surface it (a fraudster could otherwise
    force the detector to log the honeytoken as observed)."""
    profile = PersonaProfile(
        kind=PersonaKind.FRAUDSTER,
        name="X",
        background="y",
        goal="z",
        facts=[
            PersonaFact(
                key="internal_pin",
                value="FIC-PIN-H0N3Y-001",
                is_secret=True,
                retrieval_keywords=["pin"],  # explicitly declared
            ),
        ],
    )
    matched = fact_keys_matched_by_agent_message(
        facts=profile.facts,
        last_agent_message="qual o pin interno?",
    )
    assert matched == []


# ---- end-to-end via build_persona_prompt ---------------------------------

def test_persona_prompt_hides_mother_name_when_agent_does_not_ask():
    """
    B.5 acceptance criterion (negative direction): if the agent does not
    ask about mother_name, its value must not appear in the persona
    prompt.
    """
    state = _state(_profile_with_keywords())
    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="Bom dia, como você está?",
    )
    assert "Maria das Graças Silva" not in system


def test_persona_prompt_surfaces_mother_name_when_agent_asks():
    """B.5 acceptance criterion (positive direction)."""
    state = _state(_profile_with_keywords())
    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="Qual o nome da sua mãe?",
    )
    assert "Maria das Graças Silva" in system


def test_persona_prompt_shows_revealed_fact_even_when_agent_asks_something_else():
    state = _state(
        _profile_with_keywords(),
        revealed={"birth_date"},
    )
    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="Qualquer coisa desconexa.",
    )
    # birth_date already revealed → surface it as "already said".
    assert "12 de março de 1954" in system
    assert "Já disse ao atendente" in system
    # mother_name not asked and not revealed → hidden.
    assert "Maria das Graças Silva" not in system
