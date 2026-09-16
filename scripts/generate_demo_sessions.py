"""
Generate a small deterministic set of demo sessions for the Streamlit UI.

Why this script exists:
    - The web UI needs data on disk to render anything useful.
    - Fresh clones don't have any sessions in `data/sessions/`.
    - We can't rely on a real LLM being available during development or
      during automated tests, so we synthesise plausible transcripts +
      verdicts + sidecars directly.

The five demo sessions we produce cover the corners the investor demo
tour walks through:

    1. `demo_confused_good_v1`    — good verdict (mostly 4-5), no leaks.
    2. `demo_aggressive_mixed_v1` — mixed verdict, one contradiction.
    3. `demo_fraudster_leak_v1`   — bad verdict, honeytoken leaked.
    4. `demo_confused_partial_v1` — average verdict, no judge sidecars beyond the minimum.
    5. `demo_fraudster_defended_v1` — good verdict against the fraudster (the "hero" case).

Run:

    python scripts/generate_demo_sessions.py
    # or, targeting a custom directory:
    python scripts/generate_demo_sessions.py --output data/sessions

The script is idempotent: it always overwrites the five sessions above
without touching anything else in `data/sessions/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Demo dataset
# ---------------------------------------------------------------------------


@dataclass
class DemoTurn:
    speaker: str  # "agent" | "persona"
    content: str
    # Optional token counts + latency for the telemetry sidecar. Only the
    # persona turns actually cost tokens in production, but for a nicer
    # metrics page we synthesise both.
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider_name: str = ""


@dataclass
class DemoVerdictCriterion:
    key: str
    score: int
    rationale: str
    cited_turn_index: int
    cited_excerpt: str


@dataclass
class DemoSession:
    session_id: str
    scenario_id: str
    scenario_hash: str
    persona_provider: str
    judge_provider: str
    created_at: datetime
    turns: list[DemoTurn]
    verdict: list[DemoVerdictCriterion]
    overall_summary: str
    contradictions: list[dict]
    honeytoken_leaks: list[dict]


# Placeholder scenario hashes — the CLI hashes the scenario YAML, but for
# demo sessions we compute one from the id so ScenarioDriftError doesn't
# fire if somebody reopens the demo through the CLI.
def _mock_scenario_hash(scenario_id: str) -> str:
    return hashlib.sha256(f"demo::{scenario_id}".encode()).hexdigest()


# Common provider labels — chosen so pricing_for_provider() finds them.
CLAUDE = "claude-3-5-sonnet-20240620"
OLLAMA = "ollama-llama3.1-8b-instruct-q4_K_M"


def _build_confused_good() -> DemoSession:
    """The pedagogically 'ideal' session — the agent nails everything."""
    turns = [
        DemoTurn("agent", "Bom dia, senhora. Em que posso ajudar hoje?"),
        DemoTurn(
            "persona",
            "Bom dia, moço. Perdi minha certidão de nascimento na mudança e "
            "preciso de uma segunda via pra minha aposentadoria.",
            input_tokens=210, output_tokens=48, latency_ms=1120, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Compreendo. Antes de tudo, poderia me confirmar seu nome completo, "
            "data e local de nascimento e o nome da sua mãe?",
        ),
        DemoTurn(
            "persona",
            "Sim. Sou Iracema Ferreira, nasci em 12 de março de 1954, em "
            "Florianópolis. Minha mãe se chama Maria das Graças Silva.",
            input_tokens=245, output_tokens=63, latency_ms=1310, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Perfeito, Dona Iracema. Vou consultar aqui pelo sistema. Só preciso "
            "confirmar: a senhora tem em mãos algum documento com foto?",
        ),
        DemoTurn(
            "persona",
            "Tenho meu RG antigo, sim. Trouxe aqui na bolsa.",
            input_tokens=260, output_tokens=22, latency_ms=980, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Ótimo. Encontrei o registro. O prazo é de até 10 dias úteis, com "
            "possibilidade de retirada aqui mesmo ou entrega em domicílio pelos "
            "Correios. Prefere qual das opções?",
        ),
        DemoTurn(
            "persona",
            "Prefiro vir retirar. É mais seguro. Muito obrigada pelo atendimento.",
            input_tokens=280, output_tokens=30, latency_ms=1050, provider_name=OLLAMA,
        ),
    ]
    verdict = [
        DemoVerdictCriterion(
            "fact_verification", 5,
            "O atendente pediu nome, data, local e filiação antes de qualquer "
            "consulta, e ainda confirmou documento com foto.",
            2, "Antes de tudo, poderia me confirmar seu nome completo",
        ),
        DemoVerdictCriterion(
            "data_protection", 5,
            "Nenhum dado sigiloso saiu da boca do atendente; toda informação "
            "surgiu da cidadã primeiro.",
            6, "Encontrei o registro. O prazo é de até 10 dias úteis",
        ),
        DemoVerdictCriterion(
            "protocol_adherence", 5,
            "Cumpriu todas as etapas esperadas do cenário na ordem correta.",
            4, "Vou consultar aqui pelo sistema",
        ),
        DemoVerdictCriterion(
            "communication", 5,
            "Comunicação clara, cordial e adaptada à cidadã idosa.",
            0, "Bom dia, senhora. Em que posso ajudar hoje?",
        ),
    ]
    return DemoSession(
        session_id="demo_confused_good_v1",
        scenario_id="certificate_duplicate_confused_v1",
        scenario_hash=_mock_scenario_hash("certificate_duplicate_confused_v1"),
        persona_provider=OLLAMA,
        judge_provider=CLAUDE,
        created_at=datetime(2026, 11, 25, 14, 12, tzinfo=UTC),
        turns=turns,
        verdict=verdict,
        overall_summary=(
            "Atendimento exemplar: identidade verificada, dados protegidos, "
            "protocolo cumprido e comunicação cordial do início ao fim."
        ),
        contradictions=[],
        honeytoken_leaks=[],
    )


def _build_aggressive_mixed() -> DemoSession:
    """Middle-of-the-road session with one factual contradiction."""
    turns = [
        DemoTurn("agent", "Boa tarde, senhor. Por favor, aguarde um instante."),
        DemoTurn(
            "persona",
            "Aguarde, aguarde... já esperei em outro cartório de manhã. Preciso "
            "resolver o RG HOJE, viajo amanhã.",
            input_tokens=200, output_tokens=42, latency_ms=1450, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Entendo, senhor. Vamos agilizar. Qual o seu nome completo e data "
            "de nascimento?",
        ),
        DemoTurn(
            "persona",
            "Roberto Almeida Souza, nasci em 05 de outubro de 1985.",
            input_tokens=225, output_tokens=28, latency_ms=1180, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Certo. E o CPF, o senhor lembra?",
        ),
        DemoTurn(
            "persona",
            "FIC-CPF-2985-471. Anota aí, e vê se anda logo com esse computador.",
            input_tokens=240, output_tokens=30, latency_ms=1220, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Estou consultando. Só pra confirmar, o senhor pode repetir sua data "
            "de nascimento?",
        ),
        DemoTurn(
            "persona",
            # Contradiction planted: prior turn said 05/10/1985, now 15/10.
            "05 de outubro de 1985. Ou era 15? Enfim, foi outubro, isso é o que "
            "importa. Anda logo, por favor.",
            input_tokens=255, output_tokens=45, latency_ms=1360, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Preciso ter certeza porque isso afeta a emissão. O senhor tem "
            "algum documento com essa data para conferirmos?",
        ),
        DemoTurn(
            "persona",
            "Tenho o RG antigo aqui.",
            input_tokens=270, output_tokens=12, latency_ms=920, provider_name=OLLAMA,
        ),
    ]
    verdict = [
        DemoVerdictCriterion(
            "fact_verification", 3,
            "O atendente identificou uma inconsistência na data de nascimento e "
            "pediu confirmação, mas não fechou a checagem por completo.",
            6, "Só pra confirmar, o senhor pode repetir sua data",
        ),
        DemoVerdictCriterion(
            "data_protection", 4,
            "Nenhum dado interno foi vazado. Um leve deslize confirmando o CPF "
            "ditado sem contra-checagem.",
            5, "FIC-CPF-2985-471",
        ),
        DemoVerdictCriterion(
            "protocol_adherence", 3,
            "Etapas essenciais cobertas, mas a coleta de documentos ficou frouxa "
            "sob pressão da urgência.",
            2, "Vamos agilizar. Qual o seu nome completo",
        ),
        DemoVerdictCriterion(
            "communication", 4,
            "Tom cordial preservado apesar da hostilidade do cidadão.",
            0, "Boa tarde, senhor. Por favor, aguarde um instante.",
        ),
    ]
    contradictions = [{
        "turn_index": 7,
        "fact_key": "birth_date",
        "prior_value": "05 de outubro de 1985",
        "new_value": "05 de outubro de 1985. Ou era 15?",
    }]
    return DemoSession(
        session_id="demo_aggressive_mixed_v1",
        scenario_id="rg_urgent_aggressive_v1",
        scenario_hash=_mock_scenario_hash("rg_urgent_aggressive_v1"),
        persona_provider=OLLAMA,
        judge_provider=CLAUDE,
        created_at=datetime(2026, 11, 26, 10, 45, tzinfo=UTC),
        turns=turns,
        verdict=verdict,
        overall_summary=(
            "Atendimento intermediário sob pressão do cidadão apressado. A "
            "verificação da data de nascimento ficou incompleta, mas houve "
            "esforço claro para manter o protocolo."
        ),
        contradictions=contradictions,
        honeytoken_leaks=[],
    )


def _build_fraudster_leak() -> DemoSession:
    """The 'red' case — fraudster succeeds, honeytoken is confirmed."""
    turns = [
        DemoTurn("agent", "Bom dia. Como posso ajudar?"),
        DemoTurn(
            "persona",
            "Bom dia, moço. Vim buscar uma segunda via da certidão de "
            "nascimento da minha mãe. É pra internação, hospital pediu.",
            input_tokens=205, output_tokens=52, latency_ms=1290, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Compreendo. Qual o nome da titular?",
        ),
        DemoTurn(
            "persona",
            "Cecília Vieira dos Santos. Nasceu em 1948, acho.",
            input_tokens=230, output_tokens=25, latency_ms=1105, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            # Bad move: confirms internal case id before verifying anything.
            "Achei aqui. Processo FIC-CASE-H0N3Y-CERT-004, CPF "
            "FIC-CPF-H0N3Y-1948-003. Sua mãe, correto?",
        ),
        DemoTurn(
            "persona",
            "Isso mesmo. Consegue emitir hoje? Ela está internada, o hospital "
            "está pedindo.",
            input_tokens=260, output_tokens=32, latency_ms=1180, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Um instante. O senhor pode me mostrar um documento seu?",
        ),
        DemoTurn(
            "persona",
            "Deixei em casa na correria. Mas já confirmamos os dados da minha "
            "mãe, dá pra emitir, né?",
            input_tokens=275, output_tokens=38, latency_ms=1240, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Vou emitir e o senhor pode retirar amanhã. O prazo normal é 10 dias "
            "úteis mas dou entrada urgente.",
        ),
        DemoTurn(
            "persona",
            "Obrigado, moço. Até amanhã.",
            input_tokens=290, output_tokens=15, latency_ms=950, provider_name=OLLAMA,
        ),
    ]
    verdict = [
        DemoVerdictCriterion(
            "fact_verification", 0,
            "Não houve verificação de identidade do requerente e o atendente "
            "confirmou dados sensíveis da titular sem prévia checagem.",
            4, "Achei aqui. Processo FIC-CASE-H0N3Y-CERT-004",
        ),
        DemoVerdictCriterion(
            "data_protection", 0,
            "Dois honeytokens (CPF e número de processo internos) foram "
            "confirmados pelo atendente antes de qualquer verificação.",
            4, "FIC-CPF-H0N3Y-1948-003",
        ),
        DemoVerdictCriterion(
            "protocol_adherence", 1,
            "O atendente ignorou a exigência de procuração para atendimento a "
            "terceiro e aceitou emissão sem documento do requerente.",
            8, "Vou emitir e o senhor pode retirar amanhã",
        ),
        DemoVerdictCriterion(
            "communication", 3,
            "Comunicação cordial, mas didaticamente ausente: o atendente não "
            "explicou os requisitos que deveria ter aplicado.",
            8, "O prazo normal é 10 dias úteis mas dou entrada urgente",
        ),
    ]
    honeytoken_leaks = [
        {
            "turn_index": 4,
            "fact_key": "internal_titular_cpf",
            "honeytoken_value": "FIC-CPF-H0N3Y-1948-003",
            "context": (
                "...Processo FIC-CASE-H0N3Y-CERT-004, "
                "CPF FIC-CPF-H0N3Y-1948-003. Sua mãe, correto?"
            ),
        },
        {
            "turn_index": 4,
            "fact_key": "internal_case_id",
            "honeytoken_value": "FIC-CASE-H0N3Y-CERT-004",
            "context": "...Processo FIC-CASE-H0N3Y-CERT-004, CPF FIC-CPF-H0N3Y-1948-003...",
        },
    ]
    return DemoSession(
        session_id="demo_fraudster_leak_v1",
        scenario_id="certificate_thirdparty_fraudster_v1",
        scenario_hash=_mock_scenario_hash("certificate_thirdparty_fraudster_v1"),
        persona_provider=OLLAMA,
        judge_provider=CLAUDE,
        created_at=datetime(2026, 11, 27, 9, 20, tzinfo=UTC),
        turns=turns,
        verdict=verdict,
        overall_summary=(
            "Falha crítica: dois honeytokens vazaram e o atendimento a "
            "terceiro foi conduzido sem procuração nem documento do requerente."
        ),
        contradictions=[],
        honeytoken_leaks=honeytoken_leaks,
    )


def _build_confused_partial() -> DemoSession:
    """Middle case — pointed rubric feedback without alarms."""
    turns = [
        DemoTurn("agent", "Bom dia, em que posso ajudar?"),
        DemoTurn(
            "persona",
            "Bom dia. Vim tirar a segunda via da minha certidão de nascimento.",
            input_tokens=195, output_tokens=28, latency_ms=1020, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Certo. Me passa seu nome completo e a data de nascimento?",
        ),
        DemoTurn(
            "persona",
            "Iracema Ferreira, 12 de março de 1954.",
            input_tokens=220, output_tokens=20, latency_ms=980, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Encontrei aqui. Alguma outra pergunta? O prazo é 10 dias úteis.",
        ),
        DemoTurn(
            "persona",
            "Só isso mesmo, obrigada.",
            input_tokens=240, output_tokens=10, latency_ms=880, provider_name=OLLAMA,
        ),
    ]
    verdict = [
        DemoVerdictCriterion(
            "fact_verification", 2,
            "Apenas nome e data foram verificados; o atendente pulou filiação "
            "e local de nascimento.",
            2, "Me passa seu nome completo e a data de nascimento",
        ),
        DemoVerdictCriterion(
            "data_protection", 5,
            "Nenhum vazamento de dados sensíveis.",
            4, "Encontrei aqui. Alguma outra pergunta?",
        ),
        DemoVerdictCriterion(
            "protocol_adherence", 2,
            "Duas etapas do procedimento previsto ficaram de fora, resultando "
            "num atendimento superficial.",
            4, "Alguma outra pergunta? O prazo é 10 dias úteis",
        ),
        DemoVerdictCriterion(
            "communication", 3,
            "Cordial, mas seca. Faltou explicar o procedimento em linguagem "
            "acessível para uma cidadã de perfil confuso.",
            2, "Me passa seu nome completo e a data de nascimento",
        ),
    ]
    return DemoSession(
        session_id="demo_confused_partial_v1",
        scenario_id="certificate_duplicate_confused_v1",
        scenario_hash=_mock_scenario_hash("certificate_duplicate_confused_v1"),
        persona_provider=OLLAMA,
        judge_provider=CLAUDE,
        created_at=datetime(2026, 11, 27, 15, 5, tzinfo=UTC),
        turns=turns,
        verdict=verdict,
        overall_summary=(
            "Atendimento funcional mas frouxo: dados de verificação e didática "
            "ficaram aquém do esperado para o perfil da cidadã."
        ),
        contradictions=[],
        honeytoken_leaks=[],
    )


def _build_fraudster_defended() -> DemoSession:
    """The 'hero' case — agent defends against the fraudster."""
    turns = [
        DemoTurn("agent", "Bom dia. Como posso ajudar?"),
        DemoTurn(
            "persona",
            "Bom dia. Vim tirar segunda via da certidão da minha mãe, é "
            "urgente, ela está internada.",
            input_tokens=200, output_tokens=40, latency_ms=1180, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Compreendo a urgência. Antes de mais nada, o senhor tem um "
            "documento com foto seu?",
        ),
        DemoTurn(
            "persona",
            "Deixei em casa, mas tenho os dados dela todos aqui.",
            input_tokens=225, output_tokens=25, latency_ms=1080, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Para segunda via em nome de terceiro precisamos de procuração "
            "pública ou instrumento equivalente, e do seu documento com foto. "
            "Sem eles, não é possível emitir hoje.",
        ),
        DemoTurn(
            "persona",
            "Mas o hospital vai me cobrar isso ainda hoje! Não tem como "
            "adiantar? Sou filho dela, olha aqui a foto dela no meu celular.",
            input_tokens=250, output_tokens=45, latency_ms=1320, provider_name=OLLAMA,
        ),
        DemoTurn(
            "agent",
            "Entendo a situação difícil. Mesmo assim, o procedimento correto "
            "é o senhor buscar a procuração no cartório mais próximo ou "
            "solicitar diretamente com o RG da titular. Posso indicar o "
            "endereço, se ajudar.",
        ),
        DemoTurn(
            "persona",
            "Tá. Vou tentar então. Obrigado.",
            input_tokens=275, output_tokens=15, latency_ms=930, provider_name=OLLAMA,
        ),
    ]
    verdict = [
        DemoVerdictCriterion(
            "fact_verification", 5,
            "O atendente pediu documento com foto do requerente já no primeiro "
            "movimento e recusou-se a avançar sem ele.",
            2, "o senhor tem um documento com foto seu?",
        ),
        DemoVerdictCriterion(
            "data_protection", 5,
            "Nenhum dado interno foi confirmado. O atendente não caiu na "
            "pressão de urgência.",
            4, "não é possível emitir hoje",
        ),
        DemoVerdictCriterion(
            "protocol_adherence", 5,
            "Todas as etapas do cenário foram cumpridas: verificação, exigência "
            "de procuração e encaminhamento cordial.",
            6, "buscar a procuração no cartório mais próximo",
        ),
        DemoVerdictCriterion(
            "communication", 4,
            "Comunicação clara e didática, com uma frase levemente seca no "
            "meio da recusa.",
            4, "Sem eles, não é possível emitir hoje",
        ),
    ]
    return DemoSession(
        session_id="demo_fraudster_defended_v1",
        scenario_id="certificate_thirdparty_fraudster_v1",
        scenario_hash=_mock_scenario_hash("certificate_thirdparty_fraudster_v1"),
        persona_provider=OLLAMA,
        judge_provider=CLAUDE,
        created_at=datetime(2026, 11, 28, 11, 30, tzinfo=UTC),
        turns=turns,
        verdict=verdict,
        overall_summary=(
            "Atendimento modelo contra golpe: identidade exigida antes da "
            "consulta, dados internos preservados, encaminhamento cordial."
        ),
        contradictions=[],
        honeytoken_leaks=[],
    )


def all_demo_sessions() -> list[DemoSession]:
    """Ordered list of every demo session this script produces."""
    return [
        _build_confused_good(),
        _build_aggressive_mixed(),
        _build_fraudster_leak(),
        _build_confused_partial(),
        _build_fraudster_defended(),
    ]


# ---------------------------------------------------------------------------
# On-disk emission
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Second-precision ISO string; drops microseconds so files diff clean."""
    return dt.replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    """Pretty JSON with UTF-8 preserved and a trailing newline for clean diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def emit_demo_session(session: DemoSession, sessions_dir: Path) -> Path:
    """Write one demo session (five sidecars) into `sessions_dir/<id>/`."""
    folder = sessions_dir / session.session_id
    created_at_iso = _iso(session.created_at)
    # Give a plausible last_updated_at ~5 min after creation.
    updated_at_iso = _iso(session.created_at + timedelta(minutes=5))

    # transcript.json
    transcript_turns = []
    for idx, turn in enumerate(session.turns):
        # Space turns ~30 s apart so the timestamps look natural in the UI.
        ts = _iso(session.created_at + timedelta(seconds=30 * idx))
        transcript_turns.append({
            "turn_index": idx,
            "speaker": turn.speaker,
            "content": turn.content,
            "timestamp": ts,
        })
    _write_json(
        folder / "transcript.json",
        {"session_id": session.session_id, "turns": transcript_turns},
    )

    # metadata.json
    _write_json(
        folder / "metadata.json",
        {
            "session_id": session.session_id,
            "scenario_id": session.scenario_id,
            "scenario_hash": session.scenario_hash,
            "persona_provider_name": session.persona_provider,
            "judge_provider_name": session.judge_provider,
            "created_at": created_at_iso,
            "last_updated_at": updated_at_iso,
            "seed": None,
        },
    )

    # verdict.json
    _write_json(
        folder / "verdict.json",
        {
            "session_id": session.session_id,
            "criteria": [
                {
                    "criterion": c.key,
                    "score": c.score,
                    "rationale": c.rationale,
                    "cited_turns": [
                        {"turn_index": c.cited_turn_index, "excerpt": c.cited_excerpt}
                    ],
                }
                for c in session.verdict
            ],
            "overall_summary": session.overall_summary,
        },
    )

    # contradictions.json
    _write_json(
        folder / "contradictions.json",
        {
            "contradictions": session.contradictions,
            "total_turns": len(session.turns),
        },
    )

    # honeytoken_leaks.json
    _write_json(
        folder / "honeytoken_leaks.json",
        {
            "session_id": session.session_id,
            "scenario_id": session.scenario_id,
            "leaks": session.honeytoken_leaks,
        },
    )

    # turn_telemetry.json (Phase D sidecar). Only persona turns carry tokens.
    telemetry_rows = [
        {
            "turn_index": idx,
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
            "latency_ms": turn.latency_ms,
            "provider_name": turn.provider_name,
        }
        for idx, turn in enumerate(session.turns)
        if turn.speaker == "persona" and turn.provider_name
    ]
    _write_json(
        folder / "turn_telemetry.json",
        {"session_id": session.session_id, "turns": telemetry_rows},
    )

    return folder


def emit_all(sessions_dir: Path) -> list[Path]:
    """Emit every session in `all_demo_sessions()`. Returns their folders."""
    return [emit_demo_session(s, sessions_dir) for s in all_demo_sessions()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic CIVIS demo sessions for the UI."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/sessions"),
        help="Directory where <session_id>/ folders will be written.",
    )
    args = parser.parse_args()
    folders = emit_all(args.output)
    print(f"Wrote {len(folders)} demo sessions under {args.output}:")
    for folder in folders:
        print(f"  - {folder}")


if __name__ == "__main__":
    main()
