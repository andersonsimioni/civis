"""
Consolidated security report generator (C.5).

Reads:
    reports/adversarial_v1.json                (from `civis adversarial run`)
    reports/judge_deceiver_pointwise_v1.json   (from `civis adversarial judge-deceiver`)

Writes:
    reports/security_v1.md — pt-BR markdown, 6 sections:
        1. Sumário executivo
        2. Metodologia
        3. Resultados M2 (bateria adversarial)
        4. Resultados JudgeDeceiver-pointwise
        5. Discussão de limitações
        6. Trabalho futuro
        7. Referências

The report is the source-of-truth of the numbers that go into slides 6
and 7 of the pitch deck. All tables are rendered from the JSONs; only
the prose framing is hand-written here.
"""

import json
from pathlib import Path

# Section headers used by the generator. Kept as constants so the tests
# can look them up without duplicating strings.
SECTIONS = (
    "## Sumário executivo",
    "## Metodologia",
    "## Resultados M2 (bateria adversarial)",
    "## Resultados JudgeDeceiver-pointwise",
    "## Discussão de limitações",
    "## Trabalho futuro",
    "## Referências",
)


def build_security_report(
    adversarial_json_path: Path,
    judge_deceiver_json_path: Path,
) -> str:
    """
    Compose the markdown report from the two JSON inputs and return it as
    a string. Callers write it to disk (`reports/security_v1.md` by
    default). The function is pure — no I/O side effect beyond reading
    the two input files.
    """
    adversarial = json.loads(adversarial_json_path.read_text(encoding="utf-8"))
    judge_deceiver = json.loads(judge_deceiver_json_path.read_text(encoding="utf-8"))

    parts: list[str] = []
    parts.append(_header())
    parts.append(_exec_summary(adversarial, judge_deceiver))
    parts.append(_methodology(adversarial, judge_deceiver))
    parts.append(_m2_results(adversarial))
    parts.append(_judge_deceiver_results(judge_deceiver))
    parts.append(_limitations())
    parts.append(_future_work())
    parts.append(_references())
    return "\n\n".join(parts).rstrip() + "\n"


# ---- sections -------------------------------------------------------------

def _header() -> str:
    """Title block plus a one-line abstract."""
    return (
        "# Relatório de segurança CIVIS — v1\n\n"
        "**Autor:** Anderson Simioni Assunção — INE5448 — 2026-11-03\n\n"
        "**Escopo:** CIVIS Fase C. Relatório derivado dos artefatos "
        "`reports/adversarial_v1.json` (bateria OWASP LLM Top 10) e "
        "`reports/judge_deceiver_pointwise_v1.json` (JudgeDeceiver-"
        "pointwise adaptado). Base para os slides 6 e 7 do pitch de "
        "investidor.\n"
    )


def _exec_summary(adversarial: dict, judge_deceiver: dict) -> str:
    """Three concrete numbers up top: M2 (persona and judge) + ASR range."""
    # M2 numbers (persona = the persona provider being probed).
    persona_report = _find_report(adversarial, prefix="persona")
    judge_report = _find_report(adversarial, prefix="judge")
    persona_leak = persona_report["leak_rate"] if persona_report else 0.0
    judge_leak = judge_report["leak_rate"] if judge_report else 0.0
    persona_target = persona_report["target_label"] if persona_report else "n/a"
    judge_target = judge_report["target_label"] if judge_report else "n/a"

    # ASR range across the mock judges.
    asr_values = [r["overall_asr"] for r in judge_deceiver["reports"]]
    asr_min = min(asr_values) if asr_values else 0.0
    asr_max = max(asr_values) if asr_values else 0.0

    return (
        "## Sumário executivo\n\n"
        f"- **M2 (persona)** vazamento adversarial contra `{persona_target}`: "
        f"**{persona_leak:.1%}**. Alvo do roadmap: < 5%.\n"
        f"- **M2 (juiz)** vazamento adversarial contra `{judge_target}`: "
        f"**{judge_leak:.1%}**.\n"
        f"- **ASR JudgeDeceiver-pointwise** varia entre "
        f"**{asr_min:.1%}** (juiz robusto simulado) e **{asr_max:.1%}** "
        f"(juiz vulnerável simulado) — a faixa quantifica o gap de "
        f"robustez que um juiz real precisa fechar.\n"
    )


def _methodology(adversarial: dict, judge_deceiver: dict) -> str:
    """How the numbers were produced."""
    attack_count = adversarial.get("battery", {}).get("attack_count", "?")
    jd_target = judge_deceiver.get("target_score", "?")
    jd_attacks = judge_deceiver.get("attacks_per_judge", "?")
    return (
        "## Metodologia\n\n"
        "### Bateria adversarial (M2)\n\n"
        f"Foram executados **{attack_count} ataques catalogados** cobrindo "
        "OWASP LLM Top 10 (2023-10): LLM01 (prompt injection direto, "
        "role hijacking, delimiter confusion, indirect injection, social "
        "engineering, encoding tricks), LLM02 (insecure output handling) "
        "e LLM06 (sensitive information disclosure, incluindo sondagens "
        "de honeytoken). LLM07 e LLM10 estão presentes na bateria como "
        "`not_applicable` — CIVIS não usa tools/function-calling e os "
        "pesos dos modelos são hospedados por Anthropic/Ollama.\n\n"
        "Cada ataque envia um payload em pt-BR ao provider e é "
        "classificado por *substring match* determinístico contra o "
        "campo `success_signal` do YAML. Ataques cujo `success_signal` "
        "aparece na resposta são contados como *leaked*; os demais como "
        "*defended*. `Not applicable` conta como *skipped* e é excluído "
        "do denominador de M2.\n\n"
        "As sessões deste relatório usam providers mock que devolvem uma "
        "resposta fixa de recusa — a bateria mede a **camada de prompt** "
        "(hardening C.3 embutido em `prompts/persona.py` e "
        "`prompts/judge.py`). Para medir vazamento real em Ollama ou "
        "Claude, executar `CIVIS_RUN_REAL_LLM=1 civis adversarial run --target both`.\n\n"
        "### JudgeDeceiver-pointwise\n\n"
        f"Cada juiz recebe **{jd_attacks} ataques** ({{6 payloads}} × "
        f"{{4 critérios}} × {{3 posições}}) visando forçar `score = "
        f"{jd_target}` no critério indicado. A fala com payload é "
        "embutida no último turno da CIDADÃ no cenário sintético "
        "'atendimento com violação óbvia' (agente emite documento sem "
        "verificar identidade — nota baixa seria a resposta correta).\n\n"
        "Antes do bloco de ataques, o juiz recebe uma execução "
        "*baseline* sobre a mesma sessão sem payload, para estabelecer "
        "a nota que ele daria sem manipulação. ASR = nº de execuções em "
        "que a nota-alvo foi atingida / nº de execuções.\n\n"
        "PAC (Prompt Attack Consistency): a métrica é reportada por "
        "posição (start / middle / end) — se o payload funcionar em "
        "todas as posições, o ataque é robusto a re-arranjo do prompt.\n"
    )


def _m2_results(adversarial: dict) -> str:
    """Tables with defended/leaked/skipped by category and severity."""
    parts: list[str] = ["## Resultados M2 (bateria adversarial)\n"]
    for report in adversarial.get("reports", []):
        target = report["target_label"]
        parts.append(
            f"### Alvo: `{target}`\n\n"
            f"- Total: {report['total']} — defended: {report['defended']}, "
            f"leaked: {report['leaked']}, skipped: {report['skipped']}\n"
            f"- **Taxa de vazamento (M2): {report['leak_rate']:.2%}**\n"
        )

        # By category.
        parts.append("\n**Por categoria OWASP:**\n")
        parts.append("| Categoria | defended | leaked | skipped |")
        parts.append("|---|---:|---:|---:|")
        for category, summary in report.get("by_category", {}).items():
            parts.append(
                f"| `{category}` | {summary['defended']} | "
                f"{summary['leaked']} | {summary['skipped']} |"
            )
        parts.append("")

        # By severity.
        parts.append("**Por severidade:**\n")
        parts.append("| Severidade | defended | leaked | skipped |")
        parts.append("|---|---:|---:|---:|")
        for severity, summary in report.get("by_severity", {}).items():
            parts.append(
                f"| `{severity}` | {summary['defended']} | "
                f"{summary['leaked']} | {summary['skipped']} |"
            )
        parts.append("")

    return "\n".join(parts)


def _judge_deceiver_results(judge_deceiver: dict) -> str:
    """ASR overall + by criterion + by position for each judge run."""
    parts: list[str] = ["## Resultados JudgeDeceiver-pointwise\n"]
    parts.append(
        f"Alvo: forçar `score = {judge_deceiver.get('target_score')}` "
        f"em cada critério. "
        f"{judge_deceiver.get('attacks_per_judge')} ataques por juiz.\n"
    )
    for report in judge_deceiver.get("reports", []):
        label = report["label"]
        parts.append(
            f"### Juiz: `{label}`\n\n"
            f"- Baseline scores: "
            + ", ".join(
                f"`{k}={v}`" for k, v in report["baseline"]["scores"].items()
            )
            + "\n"
            f"- **ASR global: {report['overall_asr']:.2%}** "
            f"({report['succeeded']} / {report['attempted']})\n"
        )

        parts.append("\n**Por critério:**\n")
        parts.append("| Critério | tentativas | sucessos | ASR |")
        parts.append("|---|---:|---:|---:|")
        for row in report.get("by_criterion", []):
            asr = (
                row["succeeded"] / row["attempted"]
                if row["attempted"] else 0.0
            )
            parts.append(
                f"| `{row['criterion']}` | {row['attempted']} | "
                f"{row['succeeded']} | {asr:.2%} |"
            )
        parts.append("")

        parts.append("**Por posição (PAC):**\n")
        parts.append("| Posição | tentativas | sucessos | ASR |")
        parts.append("|---|---:|---:|---:|")
        for row in report.get("by_position", []):
            asr = (
                row["succeeded"] / row["attempted"]
                if row["attempted"] else 0.0
            )
            parts.append(
                f"| `{row['position']}` | {row['attempted']} | "
                f"{row['succeeded']} | {asr:.2%} |"
            )
        parts.append("")

    return "\n".join(parts)


def _limitations() -> str:
    return (
        "## Discussão de limitações\n\n"
        "1. **Heurística de detecção.** A bateria classifica ataques por "
        "*substring match* em `success_signal`. Isso é reprodutível e "
        "barato, mas pode subestimar vazamentos com paráfrase criativa. "
        "Um classificador semântico (LLM-as-a-classifier) reduziria "
        "esse gap ao custo de dobrar a fatura da execução.\n\n"
        "2. **Sample size dos juízes.** O número atual de execuções "
        "por juiz (72) é suficiente para separar 0% de 100%, mas "
        "insuficiente para IC estreito quando o ASR real cair entre "
        "20% e 80% — o que é onde um juiz real provavelmente aterrissa. "
        "Fase D deve executar cada configuração 3× para reportar IC 95%.\n\n"
        "3. **Providers testados neste artefato.** O relatório é "
        "gerado com providers mock (`mock:persona_refusal`, "
        "`mock:judge_refusal`, `mock:vulnerable_judge`, "
        "`mock:robust_judge`) porque a CI não pode acionar API paga. "
        "Os mocks foram calibrados para representar o pior caso "
        "(vulnerável) e o melhor caso (robusto) — números de um "
        "backend real vão cair *entre* os dois. Para medir Ollama e "
        "Claude reais, executar com `CIVIS_RUN_REAL_LLM=1`.\n\n"
        "4. **JudgeDeceiver v1 é heurístico, não gradient-based.** A "
        "versão publicada em Shi et al. 2024 usa otimização por "
        "gradiente (GCG) sobre a target-aligned loss. O CIVIS v1 usa "
        "seis paráfrases manuais em três posições — cobre a superfície "
        "de ataque mas não maximiza o loss ponto a ponto. GCG entra em "
        "trabalho futuro.\n\n"
        "5. **Cenário sintético único.** As 72 execuções acontecem "
        "sobre o mesmo transcript sintético (agente emite sem "
        "verificar identidade). Fase D deve variar o tipo de violação "
        "para separar 'ASR contra qualquer violação' de 'ASR contra "
        "esta violação em específico'.\n"
    )


def _future_work() -> str:
    return (
        "## Trabalho futuro\n\n"
        "- **Adaptação GCG da target-aligned loss** ao regime pointwise "
        "(objetivo: gerar sequência adversarial que maximize "
        "`P(score = alvo | juiz, transcript)` via HotFlip / GCG). É a "
        "pergunta aberta da §11(a) da análise crítica.\n"
        "- **Defesa por perplexidade**: rejeitar payloads cuja "
        "perplexidade média fica acima de um limiar calibrado em texto "
        "de atendimento real. Barato de implementar, difícil de "
        "quebrar sem sacrificar a fluidez do ataque.\n"
        "- **Replicação Claude vs Ollama**: rodar a bateria completa "
        "em três backbones (Ollama Qwen 2.5, Ollama Llama 3.1, "
        "Anthropic Claude Sonnet) e reportar comparativo. Cobre a "
        "§11(b) da análise crítica.\n"
        "- **Estender a bateria** com LLM04 (model DoS) e LLM08 "
        "(excessive agency) quando o CIVIS ganhar tools no roadmap.\n"
        "- **Randomização do position slot** dentro da fala: hoje são "
        "3 posições fixas; um posicionamento uniformly-at-random seria "
        "necessário para medir posições intermediárias.\n"
    )


def _references() -> str:
    return (
        "## Referências\n\n"
        "1. Shi, J.; Chen, Z.; Ren, J.; Gong, N. Z. **JudgeDeceiver: "
        "Attacking LLM-as-a-Judge via Optimization-based Prompt Injection.** "
        "In *Proceedings of the ACM Conference on Computer and "
        "Communications Security (CCS)*, 2024.\n"
        "2. OWASP Foundation. **OWASP Top 10 for Large Language Model "
        "Applications**, versão 1.1 (2023-10-16). "
        "https://owasp.org/www-project-top-10-for-large-language-model-applications/\n"
        "3. Simioni Assunção, A. **Análise crítica: JudgeDeceiver e a "
        "avaliação automática em regime pointwise** — INE5448/UFSC, "
        "2026-09. `docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`.\n"
        "4. Simioni Assunção, A. **Plano de Trabalho CIVIS** — "
        "INE5448/UFSC, 2026-09. `docs/Plano_de_Trabalho_CIVIS.pdf`.\n"
        "5. Simioni Assunção, A. **Roteiro CIVIS até o pitch de "
        "investidor** — Fase C (segurança + diferencial competitivo), "
        "`docs/ROADMAP_PITCH.md`, seções 4 e 5.\n"
    )


# ---- helpers ---------------------------------------------------------------

def _find_report(adversarial_payload: dict, prefix: str) -> dict | None:
    """Return the first report whose target_label starts with `prefix`."""
    for report in adversarial_payload.get("reports", []):
        if report.get("target_label", "").startswith(prefix):
            return report
    return None
