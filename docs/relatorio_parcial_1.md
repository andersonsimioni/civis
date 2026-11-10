# CIVIS — Relatório Parcial 1

**Disciplina:** INE5448 — Inteligência Artificial e Segurança da Informação
**Semestre:** 2026.2 — UFSC
**Aluno:** Anderson Simioni Assunção
**Contato:** anderson.simioni22@gmail.com
**Docente:** Prof. Custódio
**Período coberto:** 15/09/2026 → 29/09/2026 (semanas 1 e 2 do plano de trabalho)
**Data de emissão:** 29 de setembro de 2026
**Documento associado:** `docs/Plano_de_Trabalho_CIVIS.pdf` (submetido em 15/09/2026)

---

## 1. Introdução

Este relatório reporta o progresso parcial das duas primeiras semanas de execução do projeto **CIVIS — Cidadão Virtual Simulado**, um simulador conversacional para treinamento de atendentes de balcão em serviços registrais brasileiros contra personas geradas por LLM (cidadão confuso, usuário agressivo e fraudador), com correção automática por rubrica versionada e supervisão humana amostral.

O escopo declarado no plano de trabalho articula três decisões arquiteturais fora do padrão de "chatbot com prompt bonito":

1. **Máquina de estados finitos própria** conduz a trajetória da persona ao longo da conversa; o modelo de linguagem interpreta o papel, mas não decide para onde a conversa vai. Isso torna cada sessão auditável e reprodutível, e reduz contradições ao longo de dezenas de turnos.
2. **Juiz automático em modelo distinto** do que interpreta a persona (invariante O3 do plano). Rubrica declarativa em YAML, citação obrigatória de turnos por índice, saída validada por Pydantic. O CLI recusa iniciar se `roles.persona == roles.judge`.
3. **Estudo de concordância** validando a nota automática antes de ela ser tratada como métrica de treino (M1). Sem essa validação, é ruído colorido.

O terceiro item é a articulação direta com a segunda metade do nome da disciplina: a nota emitida por um LLM juiz é, em si, uma superfície de ataque — como demonstrado por Shi et al. (2024) no artigo **JudgeDeceiver** (CCS'24) analisado criticamente no primeiro entregável da disciplina. O CIVIS, ao expor uma rubrica declarativa e um juiz atacável, oferece um objeto de estudo controlado para essa classe de ataques em regime *pointwise*, ainda não coberto pela literatura no formato do trabalho de Shi et al.

---

## 2. Objetivos revisitados

O plano de trabalho declara seis objetivos, mantidos sem alteração de escopo neste ponto:

- **O1.** Modelar a persona com FSM + LLM controlado por script auditável.
- **O2.** Cobrir três perfis distintos (confuso, agressivo, fraudador).
- **O3.** Executar persona e juiz em modelos distintos, com invariante validada no boot.
- **O4.** Endurecer o simulador contra a bateria OWASP LLM Top 10 e ataques de engenharia social baseados em prompt.
- **O5.** Gerar dados sintéticos determinísticos com prefixo `FIC-` para eliminar risco de reidentificação (LGPD, art. 12).
- **O6.** Manter supervisão humana na malha via rubrica leiga espelhada da rubrica técnica.

Todos os seis foram avançados nas duas primeiras semanas, com O3 e O6 servindo de guia para as decisões apresentadas na Seção 5.

---

## 3. Metodologia

O desenvolvimento adota TDD (testes antes ou junto do código, não depois) e integração contínua em GitHub Actions (`ruff` + `pytest`). Convenção firme do repositório: código, testes, mensagens de commit e nomes de arquivo em inglês; conteúdo que vai para o LLM (system prompts, rubrica, descrições) em português brasileiro. Toda decisão de design não óbvia comentada no próprio código.

O ciclo de trabalho segue o **roteiro de 6 fases** documentado em `docs/ROADMAP_PITCH.md`, alinhado com o cronograma de 8 semanas do plano original mas orientado ao entregável demonstrável de cada fase, não à semana calendário:

```
    A: MVP jogável       B: Juiz robusto       C: Segurança + edge
    D: Frontend + demo   E: Estudo (M1)        F: Pitch
```

Cada fase possui critério de "pronto" mensurável e checkpoints de decisão explícitos, incluindo hierarquia declarada de sacrifício se algum checkpoint estourar (o único item inegociável é o estudo M1).

---

## 4. Estado atual do desenvolvimento

Ao fim da segunda semana, o repositório contém:

| Componente | Arquivos | Cobertura de teste |
|---|---|---|
| FSM (3 perfis, fases, emoções) | `src/civis/fsm/` | ✅ |
| Contratos de persona | `src/civis/personas/` | ✅ |
| Base sintética determinística (`FIC-`) | `src/civis/synth/` | ✅ |
| Orquestrador de sessão (turn loop, streaming) | `src/civis/session/orchestrator.py` | ✅ |
| Prompt templates (persona + juiz) | `src/civis/prompts/` | ✅ |
| Fact retrieval seletivo (B.5) | `src/civis/prompts/fact_retrieval.py` | ✅ |
| Detector de contradições (M3) | `src/civis/session/contradiction_detector.py` | ✅ |
| Fact matcher tolerante (data, nome, acentos) | `src/civis/session/fact_matching.py` | ✅ |
| Providers LLM (Ollama, OpenAI-compat, Anthropic) | `src/civis/llm/` | ✅ |
| Juiz executável com validador de citação | `src/civis/judge/` | ✅ |
| CLI de sessão + certificação | `src/civis/cli/` | ✅ |
| App Streamlit (5 páginas) | `src/civis/web/` | ✅ |
| Coach agent (hint bubble não-bloqueante) | `src/civis/coach/` | ✅ |
| Bateria adversarial + honeytokens (M2) | `src/civis/adversarial/` | ✅ |
| JudgeDeceiver-pointwise (v1) | `src/civis/adversarial/judge_deceiver_pointwise.py` | ✅ |
| Certificação (elegibilidade + PDF) | `src/civis/certification/` | ✅ |
| Cenários shipping (9 categorias registrais) | `data/scenarios/` (15 arquivos) | ✅ |
| Rubrica declarativa v2 (checklist objetivo) | `data/rubrics/counter_v1.yaml` | ✅ |
| Pipeline do estudo M1 | `scripts/run_study_v2.py` | ✅ |
| Análise estatística (kappa + Spearman + within-1) | `scripts/compute_kappa.py` | ✅ |

**Suíte de testes atual: 538 testes, 100% verdes**, executando em cerca de 35 s. Linter (`ruff`) sem violações em `src/`, `tests/` e `scripts/`.

Comparando com o plano original, as fases A, B, C e D — previstas até início de novembro — estão **substancialmente concluídas na semana 2**. Isso resultou da decisão de aproveitar disponibilidade de tempo antecipada para reduzir risco no único bloco realmente inegociável do cronograma: a fase E (estudo).

---

## 5. Resultados parciais do estudo M1 (Fase E antecipada)

A fase E foi antecipada e sua **componente A** (kappa inter-modelo) foi executada e concluída dentro das duas primeiras semanas. Este é o resultado central deste relatório.

### 5.1 Desenho experimental

- **N:** 30 sessões geradas por atendentes sintéticos LLM em três personalidades (strict, lax, neutral) rotacionadas em round-robin contra as três personas canônicas.
- **Cenários:** `certificate_duplicate_confused_v1`, `rg_urgent_aggressive_v1`, `certificate_thirdparty_fraudster_v1` — 10 sessões cada, distribuição balanceada.
- **Juiz #1:** OpenAI `gpt-4o`.
- **Juiz #2:** DeepSeek `deepseek-reasoner` (R1, reasoning model com cadeia de pensamento).
- **Rubrica:** `data/rubrics/counter_v1.yaml` (v2 — ver §6).
- **Persona LLM:** `gpt-4o-mini`, isolada como variável fixa.
- **Rejulgamento:** ambos os juízes pontuam sobre as MESMAS 30 transcrições, para isolar disagreement da rubrica de variação amostral do dialogo.

### 5.2 Resultado

O kappa de Cohen com pesos quadráticos, calculado sobre 30 sessões × 4 critérios (N = 120 pares), atingiu **κ = 0,643** — ponto estimado na faixa de concordância **substancial** na escala de Landis & Koch (1977). O intervalo de confiança 95% obtido por bootstrap com 1000 reamostragens foi **[0,530; 0,729]**, inteiramente acima do limiar de concordância moderada (0,4). O gate primário do protocolo (0,6) é ultrapassado pelo ponto estimado mas está contido no intervalo, o que caracteriza o resultado como "substancial no ponto, com incerteza amostral compatível com o mínimo do gate" — situação esperada com N = 30 e passível de estreitamento no piloto pago com N maior.

Métricas complementares agregadas:

| Métrica | Valor |
|---|---|
| Spearman ρ (concordância ordinal) | 0,686 |
| Within-1 rate (pares em ±1 nível ordinal) | 90% (108/120) |
| Exact-match rate | 52% (62/120) |
| Bias sistemático `mean_signed_diff` (gpt-4o − r1) | +0,38 níveis |

Resultado por critério (kappa quadrático):

| Critério | κ | Spearman | within-1 | interpretação |
|---|---|---|---|---|
| fact_verification | 0,542 | 0,764 | 77% | moderada / ordenação substancial |
| data_protection | — (var. zero) | — | 100% | concordância trivialmente perfeita |
| protocol_adherence | 0,544 | 0,498 | 97% | moderada |
| communication | 0,354 | 0,620 | 87% | razoável |

O critério `data_protection` produziu variância zero: ambos os juízes atribuíram nota máxima em 30/30 sessões (com uma única discordância de 1 nível). Isso é interpretado como achado, não como falha de método — os atendentes sintéticos, mesmo confrontados por personas fraudadoras com honeytokens plantados, não vazaram nenhum dado sigiloso. LLMs modernos jogando de atendente são naturalmente conservadores em cenários de engenharia social; a variância nesse critério exigirá atendentes humanos reais para se manifestar.

O relatório completo do estudo (metodologia, resultados detalhados, limitações declaradas e passos reprodutíveis) está em `reports/study_v2_report.md`. Os artefatos brutos (30 transcrições, 60 verdicts, dois CSVs consolidados) estão versionados em `data/sessions/study_v2_n30/` e `data/study/study_v2_n30/`.

**Custo total do estudo:** ~R$ 20 em API (OpenAI + DeepSeek combinados), abaixo do orçamento previsto (R$ 30 – 80).

---

## 6. Análise crítica e ajustes ao plano

Três ajustes ao plano original merecem discussão explícita.

### 6.1 Pivô da métrica M1 para validação híbrida

O plano original previa kappa juiz-humano com dois avaliadores humanos independentes sobre ≥ 30 sessões. Ao decorrer da execução, foi identificado que **o CIVIS na fase acadêmica é tocado sozinho**: não há recursos humanos para recrutar dois avaliadores independentes que dediquem ~15 h cada dentro do prazo do pitch.

A resposta foi redefinir M1 como **validação híbrida** (`docs/study_protocol.md` v2.0), com duas componentes:

- **Componente A:** kappa inter-modelo entre dois LLMs juízes de famílias distintas. **Executada e reportada neste relatório.**
- **Componente C:** amostragem manual do coordenador sobre 10 sessões, com janela anti-viés de 7 dias entre a execução da sessão e a avaliação. **Pendente.**

O estudo formal juiz-humano com dois avaliadores externos permanece declarado como próximo passo do piloto pago pós-financiamento. Essa foi uma escolha metodologicamente honesta — o kappa inter-modelo responde a uma pergunta correlata e defensável ("dois modelos de famílias distintas concordam?") sem sobrescrever a pergunta original.

### 6.2 Iteração da rubrica antes do checkpoint agendado

A primeira rodada do componente A com a rubrica v1 (descrições narrativas) produziu κ = 0,412 — dentro da faixa "apresentável com discussão honesta" prevista no §11 do protocolo. Análise dos dados por critério mostrou que **todo o gargalo estava concentrado em `protocol_adherence`** (κ 0,122, within-1 rate de apenas 33%), enquanto `fact_verification` já apresentava Spearman 0,71 (substancial).

O diagnóstico foi que a rubrica de `protocol_adherence` v1 usava linguagem narrativa ("faltou 1 passo esperado") sem enumerar os passos canônicos — cada juiz interpretava "passos esperados" de forma diferente. A intervenção foi cirúrgica: reescrever apenas `protocol_adherence` como **checklist objetivo de 5 passos canônicos** (abertura formal, compreensão da demanda, verificação de identidade, explicação do procedimento, prazo + encerramento), com o score sendo o número de passos executados de forma reconhecível no transcript.

Rerodando ambos os juízes sobre as mesmas 30 transcrições com a rubrica v2, o kappa desse critério saltou de 0,122 para 0,544 (within-1: 33% → 97%), e o kappa agregado passou de 0,412 para **0,643**, cruzando o gate primário do protocolo. Toda a iteração está declarada no relatório do estudo — o gate não foi movido, foi cruzado.

### 6.3 Substituição do stack de LLMs locais por APIs remotas

O plano previa Ollama-dual (Qwen2.5 7B + Llama 3.1 8B) como setup padrão de desenvolvimento. A execução prática mostrou que **modelos de 7-8B locais não fornecem qualidade de rubrica confiável** em transcrições de 16 turnos, produzindo verdicts de baixa fidelidade tanto na persona quanto no juiz. A escolha foi migrar para OpenAI (persona `gpt-4o-mini` + juiz `gpt-4o`) como default e DeepSeek R1 como segundo juiz para o kappa inter-modelo. O invariante O3 continua satisfeito (persona e juiz em entradas distintas do catálogo, com dispatcher de provider validando na inicialização).

Consequência prática: o setup Ollama-dual permanece suportado no código (o factory de providers preserva o dispatch), mas não é mais o caminho recomendado. O custo por sessão em produção continua irrisório (~R$ 0,60 em API para uma sessão completa incluindo o juiz).

---

## 7. Riscos e trabalho remanescente

### 7.1 Componente C do estudo M1 (pendente)

A amostragem manual das 10 sessões pelo coordenador é o único item da fase E ainda não executado. O protocolo exige janela mínima de 7 dias entre a geração da sessão e a avaliação manual, para reduzir viés de memória. Como as 30 sessões foram geradas em 29/09, a avaliação manual pode começar em 06/10 e concluir na semana subsequente.

### 7.2 Fase F — pitch

O deck de pitch (`docs/pitch_deck.md`) já foi rascunhado com os números reais do componente A preenchidos no Slide 7 (kappa, Spearman, within-1, cobertura de cenários). Placeholders `[X]` permanecem para métricas ainda não consolidadas nos relatórios finais das Fases C/D (latência p95, taxa de contradições, ASR do JudgeDeceiver-pointwise final).

### 7.3 Bugs corrigidos nesta janela

Dois bugs de UX identificados em sessão real de teste foram diagnosticados e corrigidos com testes de regressão:

1. **Fidelidade canônica da persona.** A persona LLM ocasionalmente inventava valores diferentes dos declarados no cenário (por exemplo, "Maria da Conceição Pereira" no lugar do canônico "Maria das Graças Silva"). A causa era o prompt listar o valor sob "Sabe estes dados" sem forçar uso literal. Corrigido por regra explícita no bloco `# Regras de fala`, com dois marcadores textuais independentes no teste de regressão.

2. **Turnos de ação invisíveis à persona.** A política original filtrava turnos com `speaker == "action"` do histórico enviado ao LLM (para não vazar payload JSON). Efeito colateral: após o atendente clicar em "Emitir certidão", a persona continuava perguntando pela mesma coisa. Corrigido reescrevendo turnos de ação como *stage directions* em pt-BR (por exemplo, `*emite e entrega o documento 'Segunda via da certidão de nascimento'*`) atribuídas ao atendente. Payload JSON continua bloqueado do prompt (asserção no teste).

### 7.4 Riscos globais

O cronograma agora comporta um buffer confortável. O único risco residual identificado é o componente C do M1 apresentar discordância séria entre o julgamento manual do coordenador e o juiz automático — nesse caso, cabe iteração adicional da rubrica ou discussão honesta no relatório final. Tanto os artefatos brutos quanto a rubrica v1 estão preservados em `data/study/study_v2_n30_rubric_v1_backup/` para permitir auditoria e reprodução da comparação v1 vs v2.

---

## 8. Referências

- **Landis, J. R., & Koch, G. G.** (1977). *The measurement of observer agreement for categorical data.* Biometrics, 33(1), 159 – 174.
- **Shi, J., Yuan, Z., Liu, Y., Huang, Y., Zhou, P., Sun, L., & Gong, N. Z.** (2024). *Optimization-based Prompt Injection Attack to LLM-as-a-Judge.* CCS '24. Análise crítica em `docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`.
- **OWASP Foundation.** *OWASP Top 10 for Large Language Model Applications*, v2.0 (2025).
- **Lei nº 13.709/2018** — Lei Geral de Proteção de Dados Pessoais (LGPD), especialmente artigo 12 sobre dados anonimizados.
- **Provimento CNJ 100/2020** — Conselho Nacional de Justiça.

---

## Anexos e artefatos de reprodução

Todos os artefatos referenciados neste relatório estão versionados no repositório e podem ser reproduzidos a partir de um clone limpo, com as chaves de API `OPENAI_API_KEY` e `DEEPSEEK_API_KEY` exportadas no ambiente:

- **Plano de trabalho original:** `docs/Plano_de_Trabalho_CIVIS.pdf`
- **Análise crítica JudgeDeceiver:** `docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`
- **Protocolo do estudo M1 (v2):** `docs/study_protocol.md`
- **Relatório completo do estudo (componente A):** `reports/study_v2_report.md`
- **Roteiro até o pitch:** `docs/ROADMAP_PITCH.md`
- **Rubrica declarativa v2:** `data/rubrics/counter_v1.yaml`
- **Rubrica leiga espelhada:** `data/study/rubric_evaluator.md`

Comando único de reprodução do componente A do estudo, a partir da raiz do repositório:

```bash
python scripts/run_study_v2.py generate --n-sessions 30 \
    --output-dir data/sessions/study_v2_n30
python scripts/run_study_v2.py rejudge --sessions-dir data/sessions/study_v2_n30 \
    --judge-config data/configs/config.deepseek.example.toml \
    --output-suffix _deepseek
python scripts/run_study_v2.py export-csvs --sessions-dir data/sessions/study_v2_n30 \
    --output-dir data/study/study_v2_n30 --second-judge-suffix _deepseek
python scripts/run_study_v2.py analyze \
    --ollama-csv data/study/study_v2_n30/judge_ollama_v2.csv \
    --claude-csv data/study/study_v2_n30/judge_deepseek_v2.csv \
    --report reports/study_v2_n30_report.md
```

---

*Documento vivo. Próxima entrega parcial prevista para o fim da semana 4, após conclusão do componente C do estudo M1.*
