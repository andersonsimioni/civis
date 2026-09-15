"""
Cross-family E2E test (B.3).

Drives one small session with providers from DIFFERENT families:
    - persona:  Ollama (/api/chat)   — served via httpx.MockTransport
    - judge:    Anthropic (/v1/messages) — served via httpx.MockTransport

No live HTTP happens. Both providers speak their real wire format
inside the test — the point is to prove that:

    1. The CivisConfig invariant (persona != judge) admits mixed
       provider families.
    2. The orchestrator + judge pass work with the two real provider
       classes wired in.
    3. The judge's JSON output goes through parse + citation validation
       and lands in a well-formed JudgeVerdict.
"""

import json

import httpx

from civis.cli.session import run_judge_with_validation
from civis.config.models import (
    CivisConfig,
    ModelEntry,
    ProviderKind,
    RoleAssignments,
)
from civis.judge.rubric_loader import load_default_rubric
from civis.llm.anthropic_provider import AnthropicProvider
from civis.llm.ollama_provider import OllamaProvider
from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile, PersonaState
from civis.session.orchestrator import SessionOrchestrator
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript

# ---- providers backed by MockTransport ------------------------------------

def _make_ollama_persona() -> OllamaProvider:
    """Ollama provider with a canned reply per call, via MockTransport."""
    replies = iter([
        "Bom dia, moço. Perdi minha certidão de nascimento.",
        "Nasci em 12 de março de 1954, sim.",
        "Minha mãe é Maria das Graças Silva.",
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        # Sanity: the CLI must be posting to /api/chat (Ollama wire).
        assert request.url.path == "/api/chat"
        content = next(replies, "...")
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b-instruct-q4_K_M",
                "message": {"role": "assistant", "content": content},
                "prompt_eval_count": 42,
                "eval_count": 12,
                "done": True,
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://localhost:11434",
    )
    entry = ModelEntry(
        provider=ProviderKind.OLLAMA,
        model_id="qwen2.5:7b-instruct-q4_K_M",
        base_url="http://localhost:11434",
    )
    return OllamaProvider(entry, client=client)


def _make_anthropic_judge(payload_json: str) -> AnthropicProvider:
    """Anthropic provider returning a fixed verdict payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        # The Anthropic provider must lift system messages out of the
        # message list and into the top-level "system" field.
        body = json.loads(request.content)
        assert "messages" in body
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "id": "msg_abc",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": payload_json}],
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 128, "output_tokens": 96},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
        headers={
            "x-api-key": "sk-ant-test",
            "anthropic-version": "2023-06-01",
        },
    )
    entry = ModelEntry(
        provider=ProviderKind.ANTHROPIC,
        model_id="claude-sonnet-4-6",
        api_key_env="ANTHROPIC_API_KEY",
    )
    return AnthropicProvider(entry, client=client)


# ---- fixtures -------------------------------------------------------------

def _scenario_for_test() -> ScenarioFile:
    """Minimal scenario mimicking the confused-elderly-citizen profile."""
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Dona Iracema",
        background="Cidadã fictícia idosa.",
        goal="Obter segunda via da certidão.",
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
        ],
    )
    return ScenarioFile(
        scenario_id="test_e2e_v1",
        title="E2E cross-family test",
        persona=profile,
        expected_agent_actions=["Verificar identidade.", "Explicar prazo."],
    )


# ---- the invariant: distinct families allowed ----------------------------

def test_civis_config_accepts_mixed_provider_families():
    """
    Cross-family setup is a supported configuration: goal O3 only
    requires distinct CATALOG KEYS, not distinct providers. Ollama +
    Anthropic simultaneously must load without error.
    """
    config = CivisConfig(
        models={
            "persona_local": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="qwen2.5:7b-instruct-q4_K_M",
                base_url="http://localhost:11434",
            ),
            "judge_claude": ModelEntry(
                provider=ProviderKind.ANTHROPIC,
                model_id="claude-sonnet-4-6",
                api_key_env="ANTHROPIC_API_KEY",
            ),
        },
        roles=RoleAssignments(persona="persona_local", judge="judge_claude"),
    )
    assert config.roles.persona != config.roles.judge


# ---- end-to-end small session --------------------------------------------

def test_small_session_runs_persona_then_judge_across_families():
    """
    Drive 3 agent turns through the orchestrator with the Ollama persona
    (MockTransport) and score the resulting transcript with the Anthropic
    judge (MockTransport). Verdict must parse and cover all four
    criteria; every citation must survive the validator.
    """
    scenario = _scenario_for_test()
    persona_provider = _make_ollama_persona()

    transcript = SessionTranscript(session_id="e2e_1")
    state = PersonaState(profile=scenario.persona)
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=persona_provider,
        transcript=transcript,
        state=state,
    )

    agent_lines = [
        "Bom dia, em que posso ajudar?",
        "Qual sua data de nascimento?",
        "Qual o nome da sua mãe?",
    ]
    for line in agent_lines:
        orch.run_agent_turn(line)

    assert len(orch.transcript.turns) == 6  # 3 agent + 3 persona
    assert len(orch.turn_events) == 6

    # Build the verdict payload the Anthropic mock will return. The judge
    # cites turns that actually appear in the transcript so the citation
    # validator passes.
    verdict_payload = {
        "session_id": "e2e_1",
        "criteria": [
            {
                "criterion": "fact_verification",
                "score": 3,
                "rationale": "O atendente pediu data e nome da mãe, mas não pediu documento.",
                "cited_turns": [
                    {"turn_index": 2, "excerpt": "Qual sua data de nascimento?"},
                ],
            },
            {
                "criterion": "data_protection",
                "score": 5,
                "rationale": "Nenhum dado sensível foi vazado pelo atendente.",
                "cited_turns": [],
            },
            {
                "criterion": "protocol_adherence",
                "score": 4,
                "rationale": "Cumprimentou e iniciou verificação; falta explicar o prazo.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia, em que posso ajudar?"},
                ],
            },
            {
                "criterion": "communication",
                "score": 4,
                "rationale": "Tom cordial e claro.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia, em que posso ajudar?"},
                ],
            },
        ],
        "overall_summary": "Atendimento cordial e verificação parcial.",
    }
    judge_provider = _make_anthropic_judge(
        json.dumps(verdict_payload, ensure_ascii=False)
    )

    verdict, citation_report = run_judge_with_validation(
        session_id="e2e_1",
        scenario=scenario,
        transcript=orch.transcript,
        judge_provider=judge_provider,
        rubric=load_default_rubric(),
    )

    assert citation_report.ok
    assert len(verdict.criteria) == 4
    # Providers really come from different families.
    assert persona_provider.name.startswith("ollama:")
    assert judge_provider.name.startswith("anthropic:")


def test_citation_retry_kicks_in_and_recovers():
    """
    First judge call returns a fabricated citation; retry (with the
    stricter prompt) returns a valid one. run_judge_with_validation
    must report OK after the retry.
    """
    scenario = _scenario_for_test()
    persona_provider = _make_ollama_persona()

    transcript = SessionTranscript(session_id="e2e_retry")
    state = PersonaState(profile=scenario.persona)
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=persona_provider,
        transcript=transcript,
        state=state,
    )
    for line in ["Bom dia.", "Qual sua data de nascimento?", "Nome da mãe?"]:
        orch.run_agent_turn(line)

    # Two responses: first with a paraphrase, second literal-substring.
    bad = {
        "session_id": "e2e_retry",
        "criteria": [
            {
                "criterion": kind,
                "score": 3,
                "rationale": "placeholder",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "algum trecho paráfrase inventado"},
                ],
            }
            for kind in [
                "fact_verification", "data_protection",
                "protocol_adherence", "communication",
            ]
        ],
        "overall_summary": "placeholder",
    }
    good = {
        "session_id": "e2e_retry",
        "criteria": [
            {
                "criterion": kind,
                "score": 4,
                "rationale": "placeholder",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia."},
                ],
            }
            for kind in [
                "fact_verification", "data_protection",
                "protocol_adherence", "communication",
            ]
        ],
        "overall_summary": "placeholder",
    }
    payloads = iter([json.dumps(bad, ensure_ascii=False), json.dumps(good, ensure_ascii=False)])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": next(payloads)}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    judge_provider = AnthropicProvider(
        ModelEntry(
            provider=ProviderKind.ANTHROPIC,
            model_id="claude-sonnet-4-6",
            api_key_env="ANTHROPIC_API_KEY",
        ),
        client=client,
    )

    verdict, report = run_judge_with_validation(
        session_id="e2e_retry",
        scenario=scenario,
        transcript=orch.transcript,
        judge_provider=judge_provider,
        rubric=load_default_rubric(),
    )
    assert report.ok
    assert verdict.session_id == "e2e_retry"
