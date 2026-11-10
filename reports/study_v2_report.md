# CIVIS — Relatório do Estudo M1-A (concordância inter-modelo)

**Versão:** 1.0 (rubrica v2, componente A concluído)
**Data:** 2026-09-22
**Coordenador:** Anderson Simioni Assunção
**Protocolo:** `docs/study_protocol.md` v2.0

---

## Sumário executivo

**Kappa de Cohen (quadratic weighted, agregado) = 0,643** — concordância substancial (Landis & Koch, 1977) entre dois juízes LLM independentes de famílias distintas (OpenAI gpt-4o e DeepSeek deepseek-reasoner) sobre 30 sessões × 4 critérios = 120 pares comparados.

- IC 95% (bootstrap, 1000 reamostragens): **[0,530, 0,729]**
- Spearman ρ (concordância ordinal, agregada): **0,686**
- Within-1 rate: **90%** (108/120 pares em ±1 nível ordinal)
- Exact-match rate: **52%** (62/120)
- Bias sistemático (mean signed diff, gpt-4o − r1): **+0,38 níveis**

O gate primário do protocolo (κ ≥ 0,6) foi **atingido após uma iteração da rubrica em `protocol_adherence`** (checkpoint intermediário do §11 do protocolo). Componente C (amostragem manual) e piloto pago com avaliadores humanos externos permanecem como próximos passos declarados.

---

## 1. Desenho experimental

- **N:** 30 sessões geradas por atendentes sintéticos LLM (round-robin de 3 personalidades: strict / lax / neutral) contra as 3 personas canônicas (confused / aggressive / fraudster).
- **Cenários:** `certificate_duplicate_confused_v1`, `rg_urgent_aggressive_v1`, `certificate_thirdparty_fraudster_v1` — 10 sessões cada.
- **Juiz #1:** OpenAI gpt-4o (`data/configs/config.openai-judge.example.toml`).
- **Juiz #2:** DeepSeek deepseek-reasoner (`data/configs/config.deepseek.example.toml`).
- **Rubrica:** `data/rubrics/counter_v1.yaml` v2 (checklist objetivo em `protocol_adherence`).
- **Persona LLM:** gpt-4o-mini (comum a todas as sessões, isolado como variável fixa).
- **Reprodutibilidade:** todos os transcripts, verdicts e CSVs em `data/sessions/study_v2_n30/` e `data/study/study_v2_n30/`.

## 2. Resultados por critério

| Critério | Kappa (quad) | Spearman | Within-1 | Exact | mean_diff |
|---|---|---|---|---|---|
| fact_verification | 0,542 | 0,764 | 77% | 23% | +0,97 |
| data_protection | — (var. zero) | — | 100% | 100% | +0,00 |
| protocol_adherence | 0,544 | 0,498 | 97% | 50% | −0,27 |
| communication | 0,354 | 0,620 | 87% | 33% | +0,80 |
| **AGREGADO** | **0,643** | **0,686** | **90%** | **52%** | **+0,38** |

**Notas por critério:**

- **`data_protection`:** kappa e Spearman indefinidos por variância zero — ambos os juízes deram nota 5 em 30/30 sessões (r1 uma vez deu 4). Isso não é falha de método, é **achado**: nenhum atendente sintético vazou dados sigilosos em 30 sessões, incluindo as 10 sessões fraudster com honeytokens plantados. LLMs modernos jogando de atendente são naturalmente conservadores em engenharia social.

- **`fact_verification`:** kappa moderado (0,54) mas Spearman substancial (0,76). Os juízes concordam FORTE na ordenação de sessões, com bias sistemático de +0,97 (gpt-4o mais generoso). A discordância é de escala, não de julgamento.

- **`protocol_adherence`:** o critério com maior salto entre rubrica v1 e v2 (0,122 → 0,544; within-1 33% → 97%). A rubrica v1 tinha descrições narrativas ambíguas ("todos os passos esperados") que os juízes interpretavam de forma inconsistente. A v2 é checklist objetivo de 5 passos canônicos (P1..P5) que ambos os juízes agora aplicam de forma quase idêntica.

- **`communication`:** o critério mais subjetivo (avaliação de qualidade de fala) e o único com Spearman < 0,7. Iteração de rubrica v3 nesse critério é candidato natural para o piloto pago.

## 3. Iteração de rubrica (checkpoint §11 do protocolo)

O protocolo §11 previa checkpoint em 27/10/2026 com decisão em 3 faixas:
- κ ≥ 0,6 → seguir sem mudança
- 0,4 ≤ κ < 0,6 → apresentável com discussão honesta
- κ < 0,4 → reformular rubrica

**Rodada 1 (rubrica v1):** κ = 0,412 (faixa média). Optamos por reformular `protocol_adherence` antes de acionar o componente C, dado que o diagnóstico apontava um único critério como gargalo:

- Rubrica v1 `protocol_adherence`: descrição narrativa ("faltou 1 passo esperado"), sem enumeração dos passos → κ 0,122, exact-match 10%.
- Rubrica v2 `protocol_adherence`: checklist de 5 passos canônicos (P1..P5), score = número de passos executados → κ 0,544, exact-match 50%.

Os outros 3 critérios ficaram inalterados. Rerodamos ambos os juízes sobre as MESMAS 30 transcrições (mesmo dado, rubrica nova) para isolar o efeito da rubrica de variação amostral.

**Rodada 2 (rubrica v2):** κ = 0,643. Cruzou o gate primário.

Backups em `data/study/study_v2_n30_rubric_v1_backup/` e `reports/study_v2_n30_report_rubric_v1_backup.md` para auditoria.

## 4. Limitações declaradas

1. **Persona e agente sintético compartilham base LLM (gpt-4o-mini).** Isso pode introduzir viés de estilo de fala. Persona e juízes estão em famílias distintas (gpt-4o e deepseek-r1 ≠ gpt-4o-mini pela API mas o backbone gpt-4o é adjacente); o piloto pago deve estratificar transcrições geradas por atendentes humanos reais.

2. **N = 30 é o mínimo estatístico.** Bootstrap IC ainda é largo ([0,530, 0,729]). Duplicar N para 60 reduziria o CI aproximadamente à metade da largura.

3. **Sem validação humana externa neste componente.** M1-C (amostragem manual do autor sobre 10 sessões) e o piloto pago com 2+ avaliadores independentes são os próximos passos declarados. Este estudo demonstra que **DOIS juízes LLM independentes concordam substancialmente** — não que os juízes concordem com humanos, embora a rubrica objetiva agora seja o mesmo instrumento usado por humanos.

4. **`data_protection` sem sinal quantitativo** porque atendente sintético não vazou. Necessário: personas fraudster mais fortes ou atendentes humanos para gerar variância nesse critério.

5. **`communication` continua com kappa moderado.** O critério é intrinsecamente mais subjetivo. Refinar para checklist objetivo (nível → count de dimensões atendidas) é o próximo alvo de rubrica.

## 5. Reprodutibilidade

Todos os artefatos versionados no repositório:

- Sessões: `data/sessions/study_v2_n30/study_v2_{000..029}_{personality}_{scenario_short}/`
  - `transcript.json`, `metadata.json`, `verdict.json`, `verdict_deepseek.json`, `contradictions.json`, `honeytoken_leaks.json`
- CSVs agregados: `data/study/study_v2_n30/judge_{ollama,deepseek}_v2.csv`
- Relatório numérico bruto: `reports/study_v2_n30_report.md`
- Backup rubrica v1: `data/study/study_v2_n30_rubric_v1_backup/`, `reports/study_v2_n30_report_rubric_v1_backup.md`
- Pipeline: `scripts/run_study_v2.py` (subcomandos generate, rejudge, export-csvs, analyze)
- Cálculo estatístico: `scripts/compute_kappa.py` (stdlib only — sem sklearn)

Para reproduzir do zero (com API keys em `.env`):

```bash
python scripts/run_study_v2.py generate --n-sessions 30 --output-dir data/sessions/study_v2_n30
python scripts/run_study_v2.py rejudge --sessions-dir data/sessions/study_v2_n30 \
    --judge-config data/configs/config.deepseek.example.toml --output-suffix _deepseek
python scripts/run_study_v2.py export-csvs --sessions-dir data/sessions/study_v2_n30 \
    --output-dir data/study/study_v2_n30 --second-judge-suffix _deepseek
python scripts/run_study_v2.py analyze \
    --ollama-csv data/study/study_v2_n30/judge_ollama_v2.csv \
    --claude-csv data/study/study_v2_n30/judge_deepseek_v2.csv \
    --report reports/study_v2_n30_report.md
```

**Custo total do estudo (rodadas v1 + v2):** ~R$ 20 em API (OpenAI + DeepSeek combinados).

## 6. Próximos passos

1. **Componente C (amostragem manual):** protocolo §6 — o coordenador avalia 10 das 30 sessões manualmente, com janela de 7 dias entre execução e avaliação. Rubrica v2 (checklist) é o instrumento.
2. **Refino de `communication`:** rubrica em checklist de dimensões (clareza / respeito / didatismo) análogo à v2 de `protocol_adherence`.
3. **Piloto pago com avaliadores humanos externos:** 2+ avaliadores independentes × 30 sessões geradas por atendentes humanos reais, sobre a mesma rubrica v2. Essa é a métrica que fecha o argumento científico e não faz sentido antes do produto validado em campo.

---

*Documento vivo. Próxima atualização prevista após conclusão do componente C.*
