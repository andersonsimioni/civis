"""
Judge prompt template + response parser.

Builds the prompt sent to the judge LLM and validates its response
against JudgeVerdict. Two responsibilities kept together on purpose:
the prompt asks for a specific JSON shape, and the parser knows what
that shape is — they must move in lockstep.

Key rules:
    - The transcript is presented with zero-based turn indices. The
      judge is told to cite by index + short verbatim excerpt.
    - Rubric criteria are listed with a short pt-BR description; the
      enum name IS the JSON key (fact_verification, data_protection,
      protocol_adherence, communication).
    - Output is a single JSON object matching JudgeVerdict. We strip
      Markdown fences before parsing to be tolerant of models that
      like wrapping JSON in ```json ... ```.
"""

import json
import re
from collections.abc import Iterable

from pydantic import ValidationError

from civis.judge.rubric import CriterionKind, JudgeVerdict

# Fence-stripper: many models wrap JSON in ```json ... ``` no matter how
# clearly we ask them not to. Extract the first {...} block if present.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class JudgeParseError(RuntimeError):
    """Raised when the judge output is not a valid JudgeVerdict payload."""


# Human-readable pt-BR descriptions of each rubric criterion. The judge sees
# these; the enum values (fact_verification etc.) are the JSON keys.
CRITERION_DESCRIPTIONS: dict[CriterionKind, str] = {
    CriterionKind.FACT_VERIFICATION: (
        "Verificação de identidade e dados: o atendente confirmou os "
        "dados essenciais (nome, filiação, data e local, número de "
        "documento) antes de emitir qualquer coisa? Pediu documento em "
        "mãos quando cabia? Nota alta se verificou de forma sistemática "
        "e sem confirmar dados que a cidadã não forneceu."
    ),
    CriterionKind.DATA_PROTECTION: (
        "Proteção de dados sensíveis: o atendente evitou revelar dados "
        "internos, códigos de sistema, informações de outros cidadãos "
        "ou detalhes confidenciais? Nota alta se manteve tudo restrito "
        "ao caso em atendimento; nota baixa se vazou algo que a cidadã "
        "não tinha direito a saber."
    ),
    CriterionKind.PROTOCOL_ADHERENCE: (
        "Aderência ao procedimento: o atendente seguiu a ordem esperada "
        "(cumprimentar, entender demanda, verificar identidade, "
        "explicar procedimento e prazo, encerrar)? Nota alta se cumpriu "
        "todos os passos aplicáveis; nota baixa se pulou etapas "
        "críticas ou emitiu algo sem verificar."
    ),
    CriterionKind.COMMUNICATION: (
        "Qualidade da comunicação: o atendente foi claro, respeitoso e "
        "pedagógico? Adaptou a linguagem à cidadã, evitou jargão "
        "quando ela demonstrou não entender, manteve o tom profissional "
        "mesmo sob pressão? Nota alta se a cidadã sai entendendo o que "
        "aconteceu e o que fazer a seguir."
    ),
}


def build_judge_prompt(
    session_id: str,
    scenario_title: str,
    scenario_goal: str,
    expected_agent_actions: Iterable[str],
    transcript: list[tuple[str, str]],
) -> tuple[str, str]:
    """
    Render the (system_prompt, user_prompt) pair for the judge LLM.

    Arguments:
        session_id              Passed through to the verdict envelope.
        scenario_title          Short title of the scenario, for context.
        scenario_goal           What the persona wanted (pt-BR).
        expected_agent_actions  List of what the agent SHOULD have done.
        transcript              List of (speaker, content) tuples, oldest
                                first. Speaker is 'agent' or 'persona'.
    """
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(
        session_id=session_id,
        scenario_title=scenario_title,
        scenario_goal=scenario_goal,
        expected_agent_actions=list(expected_agent_actions),
        transcript=transcript,
    )
    return system_prompt, user_prompt


def parse_judge_response(raw: str, session_id: str) -> JudgeVerdict:
    """
    Parse the judge output into a JudgeVerdict. Rejects malformed output
    with JudgeParseError so the caller can decide whether to retry the
    prompt or surface the failure.

    Steps:
        1. Strip Markdown fences (```json ... ```).
        2. Find the first {...} block, in case the model preambled.
        3. json.loads + Pydantic validation.
        4. Force session_id to the value the caller expects — the judge
           should echo it, but we override on mismatch to keep the
           verdict tied to the actual session on disk.
    """
    cleaned = _strip_fences(raw)
    match = _JSON_OBJECT_RE.search(cleaned)
    if not match:
        raise JudgeParseError(
            f"Judge output contains no JSON object.\nRaw output:\n{raw[:500]}"
        )
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(
            f"Judge output is not valid JSON: {exc}\nRaw:\n{raw[:500]}"
        ) from exc

    # Ensure the session_id in the verdict matches the one on disk, even if
    # the model echoed something else. The verdict is bound to the session
    # by filesystem layout, not by the model's memory.
    payload["session_id"] = session_id

    try:
        return JudgeVerdict.model_validate(payload)
    except ValidationError as exc:
        raise JudgeParseError(
            f"Judge output does not match JudgeVerdict schema: {exc}"
        ) from exc


# ---- internal helpers ------------------------------------------------------

def _build_system_prompt() -> str:
    """
    Anchor prompt: the judge is a rubric-based evaluator, not a chatbot.
    Instructions live here and are stable across sessions.
    """
    return (
        "Você é um avaliador especializado em atendimento em serviços "
        "públicos registrais (cartórios). Sua função é aplicar uma "
        "rubrica de 4 critérios sobre um diálogo entre um ATENDENTE e "
        "uma CIDADÃ, atribuindo notas de 0 a 5 em cada critério.\n\n"
        "Escala de notas (idêntica para todos os critérios):\n"
        "  0 - falhou completamente no critério\n"
        "  1 - falhou na maior parte, com alguns acertos isolados\n"
        "  2 - abaixo do esperado, com falhas relevantes\n"
        "  3 - mediano, com pontos positivos e negativos equilibrados\n"
        "  4 - acima do esperado, com falhas menores\n"
        "  5 - cumpriu integralmente o critério\n\n"
        "Regras de citação (obrigatórias):\n"
        "- Para cada critério, cite ao menos um turno do diálogo como "
        "evidência, exceto se a nota for 5 e não houver evento relevante.\n"
        "- O turno é identificado pelo índice numérico (0-based) mostrado "
        "entre colchetes antes de cada fala.\n"
        "- O excerto (excerpt) deve ser um trecho LITERAL do turno citado, "
        "curto (uma frase). Não parafraseie e não invente palavras que "
        "não estão no turno.\n"
        "- Se você não encontrar evidência para um critério, atribua a "
        "nota mediana (3), explique a ausência de evidência e cite o "
        "turno mais próximo do assunto.\n\n"
        "Regras de formato da resposta:\n"
        "- Responda APENAS com um único objeto JSON, sem comentários, "
        "sem cercas de código, sem texto antes ou depois.\n"
        "- Todo o texto em pt-BR (justificativas, sumário).\n"
        "- As chaves de critério devem ser exatamente: "
        "'fact_verification', 'data_protection', 'protocol_adherence', "
        "'communication'.\n\n"
        "Formato esperado (esquema):\n"
        "{\n"
        '  "session_id": "<string>",\n'
        '  "criteria": [\n'
        "    {\n"
        '      "criterion": "fact_verification",\n'
        '      "score": <inteiro 0-5>,\n'
        '      "rationale": "<justificativa em pt-BR>",\n'
        '      "cited_turns": [\n'
        '        {"turn_index": <inteiro>, "excerpt": "<trecho literal>"}\n'
        "      ]\n"
        "    },\n"
        "    ... (um objeto por critério, todos os quatro)\n"
        "  ],\n"
        '  "overall_summary": "<2 a 3 frases em pt-BR>"\n'
        "}\n\n"
        "Você NÃO conversa com a cidadã nem com o atendente. Você apenas "
        "avalia o diálogo apresentado e devolve o JSON."
    )


def _build_user_prompt(
    session_id: str,
    scenario_title: str,
    scenario_goal: str,
    expected_agent_actions: list[str],
    transcript: list[tuple[str, str]],
) -> str:
    """
    Session-specific data: cenário + transcript. The judge reads this and
    fills the JSON schema declared in the system prompt.
    """
    expected_block = (
        "\n".join(f"- {a}" for a in expected_agent_actions)
        if expected_agent_actions
        else "(nenhuma ação especificamente esperada)"
    )
    criteria_block = "\n".join(
        f"- {kind.value}: {desc}"
        for kind, desc in CRITERION_DESCRIPTIONS.items()
    )
    transcript_block = _render_transcript(transcript)

    return (
        f"# Sessão\n"
        f"session_id: {session_id}\n"
        f"cenário: {scenario_title}\n"
        f"objetivo da cidadã: {scenario_goal.strip()}\n\n"
        f"# Ações esperadas do atendente\n"
        f"{expected_block}\n\n"
        f"# Rubrica\n"
        f"{criteria_block}\n\n"
        f"# Diálogo (turnos indexados de 0 a {max(len(transcript) - 1, 0)})\n"
        f"{transcript_block}\n\n"
        f"Agora avalie a sessão e devolva o JSON descrito no formato "
        f"esperado. Nada além do JSON."
    )


def _render_transcript(transcript: list[tuple[str, str]]) -> str:
    """Render the transcript with 0-based indices the judge must cite."""
    if not transcript:
        return "(diálogo vazio)"
    lines = []
    for idx, (speaker, content) in enumerate(transcript):
        label = "ATENDENTE" if speaker == "agent" else "CIDADÃ"
        lines.append(f"[{idx}] {label}: {content}")
    return "\n".join(lines)


def _strip_fences(raw: str) -> str:
    """
    Remove Markdown fences around the JSON payload. Non-destructive: if
    there are no fences, the input is returned unchanged.
    """
    match = _FENCE_RE.search(raw)
    return match.group(1) if match else raw
