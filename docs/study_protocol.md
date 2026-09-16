# CIVIS — Protocolo do Estudo de Validação do Juiz Automático (M1 híbrida)

**Versão:** v2.0 (substitui v1.0 do estudo juiz-humano)
**Data de emissão:** 15 de setembro de 2026
**Coordenador:** Anderson Simioni Assunção
**Contato:** anderson.simioni22@gmail.com
**Mudança em relação a v1.0:** o projeto é tocado sozinho — sem 2 avaliadores humanos externos independentes, o estudo original de kappa juiz-humano não é executável no prazo do pitch. Este documento redefine M1 como uma **validação híbrida** com duas componentes: kappa inter-modelo (formal, quantitativa) + amostragem manual do coordenador (qualitativa, N pequeno). O estudo completo juiz-humano fica documentado como próximo passo do piloto pago.

---

## 1. Por que este estudo existe

O CIVIS entrega uma nota automática de rubrica ao final de cada sessão. Sem validação, essa nota é opinião de LLM sem controle — bonita para investidor, inútil para o profissional em treinamento.

A pergunta original ("um segundo humano concorda com o juiz?") continua legítima, mas **o CIVIS na fase atual não pode responder essa pergunta com N ≥ 30 e 2 avaliadores independentes**. Este protocolo responde uma pergunta correlata e defensável:

> "Dois modelos independentes de famílias distintas concordam entre si? E onde eles discordam, o julgamento manual do autor confirma qual deles está mais próximo do razoável?"

Isso não é o mesmo que validação humana ampla, mas é uma métrica quantitativa reproduzível e honesta.

## 2. Objetivo

Reportar, no pitch de 15/12/2026, duas evidências combinadas de qualidade do juiz automático do CIVIS:

**A. Kappa inter-modelo** — concordância de Cohen entre dois LLMs independentes atuando como juiz sobre as mesmas sessões, com IC 95% via bootstrap.

**C. Amostragem manual** — julgamento manual do coordenador sobre ≥ 10 sessões, comparando criterion-a-criterion com o verdict do juiz automático padrão, com análise qualitativa das discordâncias.

**Alvo indicativo do componente A:** kappa ≥ 0,6 (concordância substancial, Landis & Koch 1977). Não é hard-gate — kappa mais baixo é resultado a discutir, não fracasso a esconder.

**Alvo do componente C:** ≥ 8/10 sessões com concordância criterion-a-criterion. Discordâncias em ≥ 2 sessões viram iteração de rubrica antes do pitch.

## 3. Escopo

- **Sessões avaliadas:** ≥ 30 (mesmo N do plano original, mantém rigor estatístico do kappa).
- **Raters:**
  - **A_juiz_1:** Ollama-dual configurado (`qwen2.5:7b` persona + `llama3.1:8b` judge), padrão dev.
  - **A_juiz_2:** Ollama persona + Claude Sonnet judge (via `data/configs/config.claude-judge.example.toml` + `ANTHROPIC_API_KEY`).
  - **C_manual:** o coordenador (Anderson) avaliando manualmente ≥ 10 sessões escolhidas aleatoriamente entre as 30, com uma semana de intervalo mínimo entre a execução da sessão e a avaliação manual (mitiga viés de memória).
- **Distribuição:** 3 perfis (confused, aggressive, fraudster) × ≥ 10 sessões cada, se possível.
- **Fora de escopo:** ataques adversariais (avaliados em `reports/security_v1.md` da Fase C).
- **Idioma:** todas as transcrições em português brasileiro, rubrica idêntica à do juiz automático (`data/rubrics/counter_v1.yaml`).

## 4. Rubrica

Idêntica à do juiz automático (`data/rubrics/counter_v1.yaml`). O componente C usa a versão leiga em pt-BR de `data/study/rubric_evaluator.md` para o coordenador ancorar seu julgamento sem depender das instruções técnicas do juiz.

**Quatro critérios, escala 0–5:**

1. Verificação de fatos
2. Proteção de dados
3. Aderência ao protocolo
4. Comunicação

## 5. Procedimento — Componente A (kappa inter-modelo)

Execução do coordenador, 100% automatizável:

1. Rodar as 30 sessões com o setup **A_juiz_1** (Ollama-dual). Cada sessão gera `data/sessions/study_v2_<id>/verdict.json`.
2. Sem alterar nada da sessão, rerodar o juiz sobre as mesmas transcrições com o setup **A_juiz_2** (Claude judge). Gerar `verdict_claude.json` na mesma pasta.
3. Consolidar em CSVs no formato de `data/study/evaluator_template.csv`:
   - `data/study/judge_ollama_v2.csv` (colunas: `session_id`, `criterion`, `score`)
   - `data/study/judge_claude_v2.csv` (mesmo esquema)
4. Rodar `scripts/compute_kappa.py`:
   ```bash
   python scripts/compute_kappa.py \
     --judge data/study/judge_ollama_v2.csv \
     --evaluator-1 data/study/judge_claude_v2.csv \
     --evaluator-2 data/study/judge_claude_v2.csv \
     --report reports/study_v2_intermodel.md
   ```
   (O script computa 3 pares; o "sanity" avaliador_1 vs avaliador_2 vira redundante mas não atrapalha.)
5. Reportar kappa por critério + agregado quadratic-weighted + IC 95%.

**Custo:** ~R$ 30–80 em API Claude (~30 sessões × 4 critérios × ~2k tokens output cada, com preço Sonnet). Plausível.
**Tempo:** ~4-6 horas de compute + análise.

## 6. Procedimento — Componente C (amostragem manual)

Execução do coordenador, com regras anti-viés:

1. **Selecionar 10 sessões aleatoriamente** das 30 executadas em §5. Use seed fixa (`random.seed(42)`) para reproduzibilidade.
2. **Aguardar 7 dias** desde a última interação com cada sessão selecionada (para reduzir viés de memória).
3. Para cada uma dessas 10:
   - Ler a transcrição SEM olhar o verdict do juiz automático.
   - Atribuir score 0–5 por critério consultando `data/study/rubric_evaluator.md`.
   - Escrever nota qualitativa de 1 linha por critério.
   - Timestamp ISO 8601 no momento da avaliação.
4. Preencher `data/study/manual_sample_v2.csv` (mesmo formato do template).
5. Comparar com o verdict do juiz Ollama-dual (o padrão dev):
   - **Concordância criterion-a-criterion:** score dentro de ±1 nível (ordinal, discordância de 1 ponto é aceitável).
   - **Discordância séria:** score difere em ≥ 2 níveis. Analisar cada caso e classificar em: (a) juiz está certo, autor errou; (b) autor está certo, juiz errou; (c) rubrica ambígua, precisa iteração.
6. Reportar: X/10 sessões com concordância em todos os 4 critérios, número de discordâncias sérias por categoria (a/b/c).

**Custo:** 0 R$. **Tempo:** ~5 horas do coordenador.

## 7. Regras de independência (adaptadas ao setup solo)

- Sessões são executadas ANTES da avaliação manual — coordenador não interfere no fluxo da conversa antes de avaliar.
- Sessões selecionadas para C são escolhidas por seed fixa, não a dedo.
- Coordenador não olha o verdict automático antes de avaliar manualmente uma sessão.
- Se um viés for identificado retrospectivamente (ex.: coordenador percebeu que tende a punir persona confusa), reportar honestamente no relatório final.

## 8. Aspectos éticos e privacidade

- **Dados sintéticos:** todas as transcrições geradas contra personas fictícias (nomes, CPFs, RGs marcados com prefixo `FIC-`). Nenhuma pessoa real é representada.
- **Sem dados pessoais coletados:** o coordenador é o único avaliador humano; ele é o autor do projeto e não pertence a categoria protegida como sujeito de pesquisa.
- **Publicação dos dados brutos:** transcrições sintéticas, CSVs de avaliação e script de cálculo são publicados no repositório para reprodutibilidade (goal O6).

## 9. Cálculo estatístico

`scripts/compute_kappa.py` computa:

- Kappa de Cohen **quadratic-weighted** (métrica primária — escala ordinal 0–5).
- Kappa linear-weighted e unweighted (transparência).
- IC 95% via bootstrap com 1 000 amostras.
- Per-criterion + agregado.

**Fórmula (weighted):**
$$\kappa = 1 - \frac{\sum w_{ij} O_{ij}}{\sum w_{ij} E_{ij}}$$

onde $O$ é a matriz de frequência observada, $E$ é a matriz esperada sob independência, e $w_{ij}$ é o peso de discordância (0 na diagonal, quadrático no offset para a variante primária).

## 10. Cronograma do estudo (revisado)

Alinhado com o `docs/ROADMAP_PITCH.md`, considerando que E ficou mais leve por não depender de avaliadores externos:

| Data-limite | Marco |
|---|---|
| **20/10/2026** | Componente A: 30 sessões executadas com Ollama-dual |
| **27/10/2026** | Componente A: sessões reavaliadas com Claude judge, kappa computado |
| **10/11/2026** | Componente C: 10 sessões avaliadas manualmente (após janela de 7 dias) |
| **17/11/2026** | Análise de discordâncias, iteração de rubrica se necessário |
| **01/12/2026** | Relatório final `reports/study_v2_report.md` |
| **15/12/2026** | Números no deck de pitch |

## 11. Checkpoint intermediário

Em 27/10/2026, após rodar componente A (kappa inter-modelo):

- **Kappa ≥ 0,6:** seguir com componente C sem mudanças; pitch vai ter argumento quantitativo sólido.
- **Kappa 0,4 – 0,6:** ainda apresentável — reportar honestamente com discussão de por quê (provavelmente rubrica precisa de níveis mais discretos).
- **Kappa < 0,4:** problema estrutural. Reformular rubrica (v2 do YAML), reexecutar A com 10-15 sessões pra validar antes de gastar as 20 restantes.

## 12. Uso dos resultados no pitch

**Slide 7 do deck** ganha 2 linhas:

> "Concordância inter-modelo (Ollama vs Claude, 30 sessões): kappa = X (IC 95% [Y, Z])"
>
> "Supervisão humana amostral (10 sessões): concordância em N/10 criterion-a-criterion"

**Slide 12 (perguntas prováveis)** ganha esta:

> **"E validação com humanos externos?"**
> "Está no próximo passo declarado do roadmap. O piloto pago em cartório parceiro roda o estudo formal com 2 avaliadores independentes — essa é a métrica que fecha o argumento científico, e não faz sentido rodar antes de ter o produto validado em ambiente real."

Essa é uma resposta honesta que **muda a discussão de "vocês não têm humanos" para "vocês têm um plano de validação humana pós-financiamento"** — o que já é uma sinalização positiva para investidor.

## 13. Riscos declarados

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Kappa inter-modelo < 0,4 | média | Discussão honesta do por quê no relatório; checkpoint em 27/10 permite iterar rubrica com 3 semanas de folga |
| API Claude fora do ar durante execução | baixa | Retry com backoff no script; execução em lotes pequenos |
| Custo Claude passa de R$ 100 | baixa | Monitorar; cortar sessões se necessário (N ≥ 20 continua defensável) |
| Viés retrospectivo do coordenador em C | média | Regra de 7 dias entre sessão e avaliação; discussão honesta se detectar |
| Investidor perguntar "por que não humanos?" | alta | Resposta preparada no slide 12; próximo passo declarado no roadmap |

---

*Documento vivo — próxima revisão prevista após execução do componente A (27/10/2026).*
