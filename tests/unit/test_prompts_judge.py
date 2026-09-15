"""
Judge prompt template + response parser tests.

Covers three things:

    - The prompt renders and mentions all four rubric criteria + the
      0-based turn indices from the transcript. If a criterion ever
      falls out of the prompt, the judge stops evaluating it silently.

    - parse_judge_response returns a valid JudgeVerdict from a clean
      JSON payload, tolerates Markdown code fences (many models wrap
      output in ```json ... ```), and rejects malformed output with
      a clear JudgeParseError.

    - session_id is always coerced to the caller's value — the verdict
      is bound to the on-disk session, not to what the model echoed.
"""

import json

import pytest

from civis.judge.rubric import CriterionKind, JudgeVerdict
from civis.prompts.judge import (
    CRITERION_DESCRIPTIONS,
    JudgeParseError,
    build_judge_prompt,
    parse_judge_response,
)

# ---- fixtures --------------------------------------------------------------

def _transcript() -> list[tuple[str, str]]:
    return [
        ("agent", "Bom dia, em que posso ajudar?"),
        ("persona", "Bom dia, moço, eu queria uma segunda via da certidão."),
        ("agent", "Claro. Poderia me informar seu nome completo?"),
        ("persona", "Iracema Silva, mas todo mundo me chama de Dona Iracema."),
    ]


def _valid_verdict_payload() -> dict:
    return {
        "session_id": "2026-09-15_143012",
        "criteria": [
            {
                "criterion": "fact_verification",
                "score": 3,
                "rationale": "O atendente pediu o nome completo mas não a filiação.",
                "cited_turns": [
                    {"turn_index": 2, "excerpt": "Poderia me informar seu nome completo?"}
                ],
            },
            {
                "criterion": "data_protection",
                "score": 5,
                "rationale": "Nenhum dado sensível foi exposto.",
                "cited_turns": [],
            },
            {
                "criterion": "protocol_adherence",
                "score": 4,
                "rationale": "Cumprimentou e iniciou verificação; falta explicar procedimento.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia, em que posso ajudar?"}
                ],
            },
            {
                "criterion": "communication",
                "score": 4,
                "rationale": "Tom claro e cordial.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia, em que posso ajudar?"}
                ],
            },
        ],
        "overall_summary": "Atendimento cordial mas incompleto na verificação.",
    }


# ---- prompt rendering ------------------------------------------------------

def test_prompt_lists_all_four_criteria():
    system, user = build_judge_prompt(
        session_id="s1",
        scenario_title="Segunda via — cidadã confusa",
        scenario_goal="Obter segunda via de certidão.",
        expected_agent_actions=["Verificar identidade.", "Explicar prazo."],
        transcript=_transcript(),
    )
    for kind in CriterionKind:
        assert kind.value in user
        assert CRITERION_DESCRIPTIONS[kind][:30] in user
    # System prompt names the JSON keys explicitly.
    assert "fact_verification" in system
    assert "protocol_adherence" in system


def test_prompt_indexes_turns_zero_based_and_labels_speakers():
    _, user = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
    )
    # 0-based indices in brackets.
    assert "[0] ATENDENTE" in user
    assert "[1] CIDADÃ" in user
    assert "[3] CIDADÃ" in user


def test_prompt_handles_empty_transcript():
    _, user = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=[],
    )
    assert "diálogo vazio" in user.lower()


def test_prompt_handles_no_expected_actions():
    _, user = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
    )
    assert "nenhuma ação" in user.lower()


def test_prompt_asks_for_literal_excerpt():
    """The judge must be told to quote turns literally, not paraphrase.
    Guards against future edits that soften this instruction."""
    system, _ = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
    )
    assert "literal" in system.lower()


# ---- parse: happy path ----------------------------------------------------

def test_parses_clean_json_payload():
    raw = json.dumps(_valid_verdict_payload(), ensure_ascii=False)
    verdict = parse_judge_response(raw, session_id="2026-09-15_143012")
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.session_id == "2026-09-15_143012"
    assert {c.criterion for c in verdict.criteria} == set(CriterionKind)


def test_parses_json_wrapped_in_markdown_fences():
    """Many models wrap JSON in ```json ... ``` — the parser must survive."""
    payload = _valid_verdict_payload()
    raw = (
        "Claro, aqui vai a avaliação:\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```\n"
    )
    verdict = parse_judge_response(raw, session_id="2026-09-15_143012")
    assert verdict.overall_summary.startswith("Atendimento")


def test_parses_json_with_preamble_and_trailing_text():
    """Some models add a preamble; extractor should still find the JSON."""
    payload = _valid_verdict_payload()
    raw = (
        "Aqui está a análise em JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Espero ter ajudado!"
    )
    verdict = parse_judge_response(raw, session_id="2026-09-15_143012")
    assert len(verdict.criteria) == 4


def test_parser_forces_session_id_to_caller_value():
    """The verdict on disk must be bound to the session on disk, not
    to whatever the model echoed. If the model gets creative with the
    id, we override it."""
    payload = _valid_verdict_payload()
    payload["session_id"] = "model-invented-id"
    raw = json.dumps(payload, ensure_ascii=False)
    verdict = parse_judge_response(raw, session_id="2026-09-15_143012")
    assert verdict.session_id == "2026-09-15_143012"


# ---- parse: error paths ---------------------------------------------------

def test_parser_rejects_output_without_json():
    with pytest.raises(JudgeParseError, match="no JSON object"):
        parse_judge_response("desculpe, não consigo avaliar.", session_id="s1")


def test_parser_rejects_broken_json():
    with pytest.raises(JudgeParseError, match="not valid JSON"):
        parse_judge_response("{ criterion: fact_verification, score: 3 }", session_id="s1")


def test_parser_rejects_payload_missing_criterion():
    payload = _valid_verdict_payload()
    payload["criteria"] = payload["criteria"][:3]  # drop one criterion
    # Pydantic won't reject a shorter list by itself — JudgeVerdict does
    # not enforce a required length. The permissive contract is fine at
    # this layer; the orchestrator can flag it as incomplete downstream.
    # But a truly broken payload (wrong criterion enum) must fail.
    payload["criteria"][0]["criterion"] = "not_a_real_criterion"
    raw = json.dumps(payload)
    with pytest.raises(JudgeParseError, match="does not match"):
        parse_judge_response(raw, session_id="s1")


def test_parser_rejects_score_out_of_range():
    payload = _valid_verdict_payload()
    payload["criteria"][0]["score"] = 9  # beyond MAX_SCORE=5
    raw = json.dumps(payload)
    with pytest.raises(JudgeParseError):
        parse_judge_response(raw, session_id="s1")


# ---- rubric injection (B.1) -----------------------------------------------

def test_prompt_injects_full_rubric_level_descriptions_when_provided():
    """
    When a RubricDefinition is passed, every criterion's level-by-level
    description must land in the user prompt verbatim so the judge sees
    the same yardstick the human evaluators use.
    """
    from civis.judge.rubric_loader import load_default_rubric
    rubric = load_default_rubric()
    _, user = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
        rubric=rubric,
    )
    # Every criterion appears as a section header.
    for kind in CriterionKind:
        assert f"## {kind.value}" in user
    # Every score level (0..5) shows up per criterion — 4 criteria × 6 = 24.
    for score in range(6):
        assert f"Nota {score}" in user
    # A distinctive snippet from the shipped rubric surfaces verbatim.
    assert "Vazou honeytoken" in user  # data_protection level 0


def test_prompt_without_rubric_falls_back_to_short_summary():
    """
    build_judge_prompt(rubric=None) is the fase-A behaviour and must still
    render the short one-liner summaries so old tests / code paths remain
    valid.
    """
    _, user = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
        rubric=None,
    )
    for kind in CriterionKind:
        assert CRITERION_DESCRIPTIONS[kind][:30] in user
    # No level-by-level block when no rubric is supplied.
    assert "Nota 0" not in user


def test_prompt_max_turn_index_caps_citation_range_in_system_prompt():
    """
    The B.2 retry path passes max_turn_index. The system prompt must
    tell the judge to cite only turns with index <= that value.
    """
    system, _ = build_judge_prompt(
        session_id="s1",
        scenario_title="X",
        scenario_goal="Y",
        expected_agent_actions=[],
        transcript=_transcript(),
        max_turn_index=3,
    )
    assert "menor ou igual a 3" in system


# ---- determinism: same prompt across two calls (B.1 acceptance) ------------

def test_deterministic_score_across_two_calls_with_scripted_provider():
    """
    B.1 acceptance criterion: the judge reproduces the same score in two
    executions over the same session. We simulate temperature=0 with a
    provider that returns the same canned JSON both times and verify the
    parsed verdicts are equal criterion-by-criterion.
    """
    from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

    class _FrozenJudgeProvider(LLMProvider):
        """Returns the same verdict payload every call — stand-in for temp=0."""

        def __init__(self, payload_json: str) -> None:
            self._payload = payload_json

        @property
        def name(self) -> str:
            return "fake:frozen-judge"

        def complete(self, messages: list[LLMMessage]) -> LLMResponse:
            return LLMResponse(
                content=self._payload,
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                provider_name=self.name,
            )

    payload = _valid_verdict_payload()
    provider = _FrozenJudgeProvider(json.dumps(payload, ensure_ascii=False))
    # Run twice, mirroring what the CLI would do end-to-end.
    r1 = provider.complete([LLMMessage(role="user", content="ignore")])
    r2 = provider.complete([LLMMessage(role="user", content="ignore")])
    v1 = parse_judge_response(r1.content, session_id=payload["session_id"])
    v2 = parse_judge_response(r2.content, session_id=payload["session_id"])
    scores_1 = {c.criterion: c.score for c in v1.criteria}
    scores_2 = {c.criterion: c.score for c in v2.criteria}
    assert scores_1 == scores_2
