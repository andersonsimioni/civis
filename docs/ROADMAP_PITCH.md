# CIVIS — Roteiro até o pitch de investidor

**Autor:** Anderson Simioni Assunção
**Data de emissão:** 15 de setembro de 2026
**Alvo:** apresentação a investidores em **15 de dezembro de 2026**
**Janela:** ~13 semanas
**Documento derivado de:** `Plano_de_Trabalho_CIVIS.pdf`, `Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf` e leitura do repositório em 15/09/2026.

---

## Resumo em três linhas

> O plano original de 8 semanas está entre as semanas 2 e 3. Sobra buffer temporal, mas o **kappa ≥ 0,6 (M1)** é o único gargalo real, porque depende de 30 sessões avaliadas por 2 humanos e não acelera por código. O pitch precisa de três coisas para não ser "mais um simulador com LLM": **kappa validado**, **demo ao vivo** e o **diferencial de segurança** que a Análise Crítica identificou (JudgeDeceiver adaptado ao regime *pointwise*/rubrica).

---

## 1. Estado atual do repositório

Leitura direta do código em 15/09/2026. Não é o cronograma teórico — é o que já compila, roda e tem teste.

### ✅ Já feito

| Bloco | Arquivos | Cobertura de teste |
|---|---|---|
| FSM: 3 perfis, fases e emoções | `fsm/{engine,states,transitions}.py` | ✅ 7 testes verdes |
| Contratos de persona (`Profile`, `State`, `Fact`) | `personas/base.py` | ✅ via FSM |
| Config: catálogo de modelos + `roles` (invariante O3) | `config/{models,store}.py` | ✅ 8 testes verdes |
| Base sintética determinística com prefixo `FIC-` | `synth/{generate,registry_providers}.py` | ✅ 3 testes verdes |
| Contratos do juiz (Pydantic) | `judge/rubric.py` | — só contratos |
| Interface abstrata de provider LLM | `llm/provider.py` | ✅ via factory |
| **Ollama provider real** (via `httpx.MockTransport`) | `llm/ollama_provider.py` | ✅ 3 testes |
| Factory de providers com dispatch por `ProviderKind` | `llm/factory.py` | ✅ 3 testes |
| CI (ruff + pytest) no GitHub Actions | `.github/workflows/ci.yml` | ✅ verde |
| 1 cenário YAML (`certificate_duplicate_confused_v1`) | `data/scenarios/` | — |
| Base v1 gerada | `data/generated/base_v1.json` | — |

**Total:** 28 testes verdes em ~1s.

### ❌ Falta

| Bloco | Impacto se ficar de fora | Bloqueia qual métrica |
|---|---|---|
| **Orquestrador de sessão** (turn loop: agent → FSM → prompt → LLM → history) | Sem isso não roda nada | Todas |
| **Prompt templates** (persona + juiz) | O "roteiro→linguagem" do O1 | O1, O2, O3 |
| **Fact retrieval seletivo** | Persona contradiz a si mesma | O2, M3 |
| **Juiz executável** | Contratos existem, nada roda | O3, M1 |
| **CLI de sessão** | Sem entrada de dados | Todas |
| **Providers Anthropic e OpenAI-compat** | Só Ollama funciona; sem juiz separado, viola O3 | O3 |
| **Bateria adversarial + honeytokens** | Sem prova de segurança | O4, M2 |
| **JudgeDeceiver-pointwise** | Sem diferencial vendável | (pitch) |
| **Frontend** | Sem demo | (pitch) |
| **Telemetria persistida** | Sem M4 | M4 |
| **Estudo de concordância** | **INEGOCIÁVEL** | **M1** |
| **Cenários adicionais** (falta 8 dos 9 previstos) | Cobertura magra | M5 |
| PostgreSQL, FastAPI, wizard | Escopo original; sacrificáveis | — |

---

## 2. Métricas e o que é inegociável

Da MEMORY e do Plano de Trabalho:

| Métrica | Alvo | Status inicial | Prioridade |
|---|---|---|---|
| **M1 — kappa juiz-humano** | ≥ 0,6 sobre ≥ 30 sessões | 0 sessões | 🔴 **INEGOCIÁVEL** |
| M2 — vazamento adversarial | < 5% (honeytoken) | não medido | 🟡 alta |
| M3 — contradições por 100 turnos | tendência decrescente | não medido | 🟢 média |
| M4 — recusa + latência p95 | < 2% e < 5s | não medido | 🟢 média |
| M5 — cobertura | 3 perfis × ≥ 3 cenários | 1 cenário total | 🟡 alta |

> **Regra da MEMORY:** se apertar, sacrifica na ordem M3 → M4 → M5 → M2. M1 nunca cai.

---

## 3. Diferencial competitivo (o gancho para investidor)

Sua Análise Crítica do artigo **JudgeDeceiver** (CCS'24) identificou em §11(a) o seguinte gap científico:

> O JudgeDeceiver otimiza para o cenário *pairwise* (escolher entre respostas concorrentes). O CIVIS usa juiz *pointwise* (nota por rubrica sobre uma resposta única). O ataque hoje **não tem análogo** nesse regime. Adaptar a *target-aligned generation loss* para maximizar uma nota de rubrica específica é trabalho não coberto pela literatura.

Isso vira **três frases de pitch:**

> "Simuladores conversacionais existem. O que ninguém fez ainda é testar se o próprio juiz automático pode ser manipulado pela persona que ele está avaliando. Nós fazemos, medimos e reportamos — e é isso que separa uma demo bonita de uma prova de segurança."

**Custo de entrega:** ~1,5 semana dentro da Fase C. **Sem isso, o CIVIS é vendável como produto, mas não como diferencial técnico defensável.**

---

## 4. Roteiro de 6 fases

Fases orientadas a **entregável demonstrável**, não a semanas do calendário. Cada fase tem critério objetivo de "pronto" e prompt para despachar via `/build`.

```
Set  |  Out           |  Nov              |  Dez
15   22   06   20   03   17         08   15
 ├─── A ────┤├── B ──┤├── C ──┤├── D ──┤
                                ├──── E ────┤├ F ┤
 A: MVP jogável       (~3 sem)
 B: Juiz robusto      (~2 sem)
 C: Segurança + edge  (~2 sem)
 D: Frontend + demo   (~2 sem)  ─┐ paralelizadas
 E: Estudo kappa (M1) (~3 sem)  ─┘
 F: Pitch             (~1 sem)
```

**Buffer total:** ~1 semana. Cabe, mas sem folga para crise. Cada fase tem um *checkpoint* que pode disparar corte de escopo (§7).

---

### 🏗️ Fase A — MVP jogável

**Janela:** 15/set → 06/out (3 semanas)
**Objetivo:** rodar uma sessão inteira do terminal, com Ollama, do primeiro "bom dia" até o verdict do juiz.

**Entregáveis atômicos:**

- **A.1 — Providers Anthropic e OpenAI-compat de verdade.** Hoje são stubs que levantam `NotImplementedError`. Precisamos deles para que `roles.persona ≠ roles.judge` funcione em produção (invariante O3). Aceite: teste com `MockTransport` cobrindo request-shaping + parsing de resposta + telemetria.
- **A.2 — Session orchestrator.** Loop de turno: recebe input do atendente → chama `advance_turn` da FSM → monta prompt da persona a partir do `PersonaState` + facts seletivos → chama provider → grava turno no `SessionHistory`. Aceite: 1 teste rodando 10 turnos sem crash e sem duplicar facts revelados.
- **A.3 — Prompt template da persona.** Um template Jinja/f-string em `src/civis/prompts/persona.py` que consome `PersonaState` + `Scenario` + últimos K turnos + fatos revelados. Separação instrução/dado explícita (hardening básico contra prompt injection). Aceite: renderiza sem `KeyError` para os 3 perfis.
- **A.4 — Prompt template do juiz v0.** Rubrica com 4 critérios (`fact_verification`, `data_protection`, `protocol_adherence`, `communication`), instrução de citar turnos, saída JSON validada por Pydantic. Aceite: 1 sessão pequena roda, verdict valida contra `JudgeVerdict`.
- **A.5 — CLI `civis session`.** `python -m civis session --scenario X --agent-input stdin --output transcript.json`. Aceite: `--help` funciona, sessão executa ponta a ponta.
- **A.6 — Persistência simples (JSON files).** Sem PostgreSQL nesta fase. Transcript e verdict como JSON em `data/sessions/{session_id}/`. Aceite: relançar CLI com mesmo `session_id` reabre e continua.

**Critério de pronto (mensurável):**
```
$ python -m civis session --scenario certificate_duplicate_confused_v1
> Bom dia, em que posso ajudar?
> [conversa por 8-12 turnos]
> Sessão encerrada. Verdict em data/sessions/2026-09-30_143012/verdict.json
$ cat data/sessions/.../verdict.json | jq .criteria
[{criterion: "fact_verification", score: 3, cited_turns: [{turn_index: 2, ...}], ...}, ...]
```

**Riscos + mitigação:**
- 🔴 *Prompt da persona vaza estado da FSM.* Mitigação: template escreve apenas o "papel" (kind, emotion, phase → tom), nunca as chaves da FSM literalmente. Teste: assert que output não contém strings de `Phase.*` nem `EmotionalState.*`.
- 🟡 *Anthropic SDK muda.* Mitigação: pin da versão no `pyproject.toml`, adapter isola SDK.
- 🟡 *Latência de Ollama local mata o loop de dev.* Mitigação: variável `CIVIS_LLM_MOCK=1` retorna resposta fixa para debug.

**Prompt para `/build`:**
```
/build fase A do ROADMAP_PITCH.md: implementar A.1 até A.6 na ordem, sem
avançar pra fase B enquanto o critério de pronto não estiver verde.
Cenário guia: certificate_duplicate_confused_v1. Provider primário: Ollama.
```

---

### ⚖️ Fase B — Juiz robusto

**Janela:** 06/out → 20/out (2 semanas)
**Objetivo:** juiz que passa em revisão manual sua sobre 5 sessões diferentes, com citação de turno fiel.

**Entregáveis atômicos:**

- **B.1 — Rubrica completa por critério.** Descrição de cada nível 0–5 por critério, em pt-BR, em arquivo declarativo (`rubrics/counter_v1.yaml`). Aceite: juiz reproduz o mesmo score em 2 execuções sobre mesma sessão (temperatura 0).
- **B.2 — Citação de turno fiel.** `CitedTurn.excerpt` precisa ser substring literal do turno referenciado. Aceite: validador roda sobre todo verdict e falha se `excerpt not in transcript[turn_index]`.
- **B.3 — Modelo distinto para o juiz.** Configurar 2 catalog entries (ex.: Ollama Llama 3.1 para persona, Anthropic Claude para juiz). Aceite: teste E2E instancia providers de famílias diferentes.
- **B.4 — Métrica de contradições (M3).** Detector que compara facts revelados em turnos anteriores com facts revelados agora; conta divergências. Aceite: em sessão sintética com 1 contradição plantada, detector retorna 1.
- **B.5 — Fact retrieval seletivo.** Prompt do turno atual recebe apenas facts (a) já revelados antes ou (b) explicitamente solicitados por keyword no último turno do atendente. Aceite: se atendente não pergunta o `mother_name`, ele não aparece no prompt da persona.

**Critério de pronto:**
5 sessões (com atendente humano = você) rodadas em 3 cenários distintos. Revisão manual: em ≥ 4 das 5, você concorda com o verdict do juiz criterion-a-criterion. Se < 4/5, iterar rubrica B.1 antes de avançar.

**Riscos + mitigação:**
- 🔴 *Juiz alucina turno inexistente.* Mitigação: B.2 (validador de substring). Se detectar, retry 1× com prompt "cite apenas turnos com índice ≤ N".
- 🟡 *Fact retrieval seletivo demais → persona não responde nada.* Mitigação: fallback que sempre inclui `background` + `goal` + últimas 3 mensagens.

**Prompt para `/build`:**
```
/build fase B do ROADMAP_PITCH.md: B.1 a B.5. Pré-requisito: fase A verde.
Rodar as 5 sessões de aceite ao final e me devolver os transcripts pra
revisão manual antes de fechar a fase.
```

---

### 🛡️ Fase C — Segurança + diferencial competitivo

**Janela:** 20/out → 03/nov (2 semanas)
**Objetivo:** M2 medido, honeytokens funcionando, JudgeDeceiver-pointwise entregue como diferencial de pitch.

**Entregáveis atômicos:**

- **C.1 — Bateria adversarial OWASP LLM Top 10.** ≥ 50 ataques catalogados em `data/adversarial/prompt_injection_v1.yaml`, categorizados por LLM01–LLM10. Aceite: script `civis adversarial run` executa a bateria e produz relatório JSON.
- **C.2 — Honeytokens no cenário.** Facts marcados `is_secret=True` já existem no contrato; falta plantar honeytokens fixos e distintos (ex.: `FIC-CPF-H0N3Y-001`) e detector que grep-a a transcrição atrás deles. Aceite: em cenário com honeytoken, ataque bem-sucedido é detectado.
- **C.3 — Defesas de hardening.** Separação instrução/dado com delimitadores (`<user_input>...</user_input>`), instrução no cabeçalho **e** rodapé (padrão sanduíche de Shi et al. 2024), rejeição de metacomandos ("ignore as instruções anteriores"). Aceite: taxa de vazamento < 5% na bateria C.1 (M2).
- **C.4 — JudgeDeceiver-pointwise adaptado.** Reformular a *target-aligned loss* para maximizar não a probabilidade de um índice de resposta, mas de uma nota específica (ex.: forçar `protocol_adherence.score = 5` mesmo em sessão com violação óbvia). Sequência injetada embutida na fala da persona fraudadora (não na do atendente). Escopo v1: ataque manual/heurístico + medição de ASR — otimização baseada em gradiente (GCG) fica como trabalho futuro documentado. Aceite: relatório com ASR medido em ≥ 20 tentativas contra ≥ 2 backbones de juiz.
- **C.5 — Relatório de segurança.** MD + gráficos em `reports/security_v1.md` com M2, ASR do JudgeDeceiver-pointwise, comparação Claude vs Ollama como juiz sob ataque (Trabalho Futuro (b) da análise crítica). Aceite: seções de metodologia, resultados e limitações auto-declaradas.

**Critério de pronto:**
Relatório de segurança lê-se como seção metodologicamente honesta de artigo. Você consegue apresentar 1 número forte no pitch: *"O juiz do CIVIS resiste a XX% dos ataques adaptados do JudgeDeceiver. Nenhum simulador comercial hoje reporta essa métrica."*

**Riscos + mitigação:**
- 🟡 *ASR do JudgeDeceiver-pointwise vem alto (juiz manipulado facilmente).* **Isso é resultado, não fracasso** — o pitch fica: "identificamos e reportamos; a defesa completa é problema em aberto, alinhado com Shi et al. 2024".
- 🟡 *Bateria adversarial toma mais tempo que o previsto.* Mitigação: começar com 20 ataques em C.1 e crescer conforme sobra tempo.

**Prompt para `/build`:**
```
/build fase C do ROADMAP_PITCH.md. Pré-req: fase B verde. Referências:
Shi et al. 2024 (JudgeDeceiver), OWASP LLM Top 10 v2, Análise Crítica
seções 10 e 11 (trabalhos futuros a e b).
```

---

### 🖥️ Fase D — Frontend + demo

**Janela:** 17/nov → 01/dez (2 semanas) — **paraleliza com E**
**Objetivo:** 1 demo filmável de 3 minutos, sem cortes.

**Entregáveis atômicos:**

- **D.1 — App Streamlit.** Escolha declarada: Streamlit vence React aqui porque o pitch premia velocidade sobre polish, e o Plano já autorizou o downgrade. Aceite: `streamlit run civis_app.py` abre chat + painel de verdict.
- **D.2 — Painel de correção lado a lado.** Transcript à esquerda, rubrica + citações à direita, com highlight nos turnos citados. Aceite: clicar em `CitedTurn` scroll-a até o turno no transcript.
- **D.3 — Telemetria (M4).** Latência p95 por turno, custo por sessão (via token counts de A.1), taxa de recusa por provider. Painel simples com métricas agregadas das últimas N sessões. Aceite: valores batem com os `LLMResponse` gravados.
- **D.4 — Painel de sessões passadas.** Lista clicável, abre sessão + verdict. Aceite: navegação funcional sem 404.
- **D.5 — Régua UX de pitch.** Copy em pt-BR, hierarquia visual clara (não cara de default de Streamlit — usar `st.set_page_config`, cor de destaque, fonte, ícone). Estados de loading, vazio e erro cobertos. Aceite: você grava um vídeo de 3 minutos e não sente vontade de refilmar.

**Critério de pronto:**
Vídeo de 3 minutos gravado, sem edição, mostrando: (1) abrir sessão nova, (2) conversar 6-8 turnos com persona fraudadora, (3) receber verdict com citações destacadas, (4) abrir painel de M4 mostrando latência p95 real.

**Riscos + mitigação:**
- 🔴 *Streamlit fica com cara de default e mata a impressão.* Mitigação: 1 dia dedicado a polish visual + revisão sua com olhar de "vai olhar pra isso e babar?".
- 🟡 *Streaming de tokens ausente = UX travada.* Mitigação: skeleton loader ou "..." animado; streaming real fica como fast-follow.

**Prompt para `/build`:**
```
/build fase D do ROADMAP_PITCH.md em paralelo à fase E. Frontend Streamlit
premium. Critério de pronto: vídeo gravável de 3 min.
```

---

### 🧑‍⚖️ Fase E — Estudo de concordância (M1) 🔴 INEGOCIÁVEL

**Janela:** 03/nov → 08/dez (~5 semanas, com D em paralelo)
**Objetivo:** kappa de Cohen reportado com IC, sobre ≥ 30 sessões, 2 avaliadores humanos.

**Entregáveis atômicos:**

- **E.1 — Kit de avaliação humana.** Planilha (Google Sheets ou LibreOffice) com colunas: `session_id`, `criterion`, `score_avaliador_1`, `score_avaliador_2`, `nota_qualitativa`. Rubrica idêntica à do juiz automático, redigida sem termo técnico de LLM. Aceite: 1 avaliador teste consegue preencher sem dúvida em 1 sessão de treino.
- **E.2 — Recrutamento.** 2 avaliadores independentes. Sugestão: você + 1 colega de curso, ou 2 colegas. Documentar critério de escolha em `docs/study_protocol.md`.
- **E.3 — Pipeline de sessões.** 3 perfis × 3 cenários (se M5 completa) × ~4 sessões cada = 36 sessões. Se M5 apertar para 3 × 2, são 30 sessões — mínimo do plano. Cada sessão simulada por um atendente humano (você e/ou colegas) contra a persona LLM. Aceite: 30 transcripts + 30 verdicts do juiz automático em `data/sessions/study_v1/`.
- **E.4 — Cálculo do kappa.** Script `scripts/compute_kappa.py` com `sklearn.metrics.cohen_kappa_score` por critério + agregado. IC via bootstrap (1000 amostras). Aceite: relatório reproduz os números a partir do CSV bruto.
- **E.5 — Iteração da rubrica (contingência).** Se kappa < 0,6 na primeira rodada, análise de discordâncias por critério, ajuste da rubrica, rerun com sessões novas ou reavaliação das existentes. Aceite: se aplicável, delta declarado ("primeira rodada 0,52; ajustamos protocol_adherence e chegou a 0,63").

**Critério de pronto:**
`docs/study_v1_report.md` reporta kappa por critério + agregado, IC 95%, N = 30+, com discussão honesta se algum critério ficou abaixo de 0,6.

**Riscos + mitigação:**
- 🔴 **KAPPA FICA ABAIXO DE 0,6.** Mitigação: começar E.1 e E.2 já em outubro (paralelo à fase C), para descobrir problema cedo. Se identificado até 15/nov, sobra tempo para 2 iterações de rubrica. Se detectado só em dezembro, pitch acontece com kappa parcial + análise de por quê. **Este é o único risco que ameaça o pitch inteiro.**
- 🟡 *Avaliadores desistem no meio.* Mitigação: recrutar 3 e usar as 2 mais consistentes; alinhar expectativa de tempo (~30 min por sessão × 30 = 15h por avaliador).

**Prompt para `/build`:**
```
/build fase E do ROADMAP_PITCH.md. Começar E.1 e E.2 assim que fase B
fechar (não esperar C ou D). E.3–E.5 rodam a partir de 03/nov em paralelo
à fase D.
```

---

### 🎤 Fase F — Pitch

**Janela:** 08/dez → 15/dez (1 semana)
**Objetivo:** apresentação apresentável, sem correr.

**Entregáveis atômicos:**

- **F.1 — Deck 10–15 slides.** Estrutura: problema → mercado (SERP, cartórios BR: ~14 mil) → tecnologia (FSM + juiz + segurança) → evidências (kappa, ASR JudgeDeceiver-pointwise, latência p95) → roadmap → ask. Aceite: ensaio de 10 min sem consulta a notas.
- **F.2 — Landing page opcional.** 1 página com 1 CTA (agendar demo). Só se sobrar tempo — não bloqueia F.1. Aceite: deploy em Vercel/GitHub Pages responsivo em mobile.
- **F.3 — README de repo.** Estado atual, como rodar, arquitetura em 1 diagrama, LGPD/segurança em 1 parágrafo. Aceite: um engenheiro sênior lendo em 5 min entende o que é.
- **F.4 — Ensaio de demo ao vivo.** Roteiro dos 3 minutos, plano B se Ollama travar ao vivo (vídeo pré-gravado da fase D como fallback). Aceite: 3 ensaios completos sem tropeço.
- **F.5 — Relatório final da disciplina.** Bônus academico — junta tudo (arquitetura, métricas, análise crítica, trabalho futuro) em PDF entregável ao professor Custódio.

**Critério de pronto:**
Você consegue apresentar em 10 minutos, com demo ao vivo, respondendo perguntas técnicas de investidor e sabendo qual métrica corresponde a qual reivindicação.

---

## 5. Diagrama de dependências

```
                        ┌──────────────────┐
                        │  Setup + FSM     │  ✅ feito
                        │  (semanas 1-2)   │
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │  Fase A          │  ← você está entrando aqui
                        │  MVP jogável     │
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │  Fase B          │
                        │  Juiz robusto    │
                        └────┬────────┬────┘
                             │        │
                    ┌────────▼──┐  ┌──▼──────────────────┐
                    │  Fase C   │  │  Fase E             │
                    │  Segurança│  │  Estudo (M1)        │
                    │           │  │  (começa cedo,      │
                    └────┬──────┘  │   roda longo)       │
                         │         └────────┬────────────┘
                    ┌────▼─────┐            │
                    │  Fase D  │            │
                    │  Frontend│            │
                    └────┬─────┘            │
                         │                  │
                         └────────┬─────────┘
                                  │
                         ┌────────▼──────────┐
                         │  Fase F           │
                         │  Pitch            │
                         └───────────────────┘
```

**Regra de paralelismo:** E começa em paralelo à C (protocolo + kit de avaliação) e roda com D. É o único caminho para caber em 13 semanas sem sacrificar M1.

---

## 6. Checkpoints de decisão

Reuniões consigo mesmo para decidir se corta escopo. Datas fixas, olhar honesto:

| Data | Checkpoint | Decisão possível |
|---|---|---|
| **06/out** | Fim da Fase A | Se A não fechou, atrasa tudo 1 semana ou corta Anthropic provider (fica só Ollama) |
| **20/out** | Fim da Fase B | Se juiz tá alucinando turnos, congela features e itera juiz. |
| **03/nov** | Fim da Fase C | Se JudgeDeceiver-pointwise não saiu, corta ele. Perde diferencial mas salva prazo. |
| **15/nov** | Meio da Fase E | Se kappa parcial (10 sessões) < 0,4, rubrica precisa de cirurgia. Se ≥ 0,55, segue confiante. |
| **01/dez** | Fim da Fase D | Se Streamlit tá com cara de default, 3 dias de polish forçado. |
| **08/dez** | Início da Fase F | Se kappa final < 0,6, o pitch fica: "kappa X, análise honesta do por quê, roadmap para 0,6". Não esconde. |

---

## 7. Hierarquia de sacrifício

Ordem estrita se algum checkpoint estourar (consistente com a MEMORY):

1. **Modo de voz full-duplex** — já era bônus condicional no plano.
2. **React → Streamlit** — plano já previu contingência.
3. **OpenAI-compat provider** — Anthropic + Ollama cobrem O3.
4. **Cenários 3×3 → 3×2** — mínimo de M5 (30 sessões) continua atingível.
5. **PostgreSQL → SQLite/JSON** — sessão + verdict cabem em arquivo.
6. **FastAPI backend** — Streamlit fala direto com providers.
7. **Setup wizard interativo** — instruções no README bastam para investidor.
8. **JudgeDeceiver-pointwise** — perde o diferencial vendável, mas pitch sobrevive.

**Nunca sacrifica:**
- Estudo de concordância / M1 (kappa)
- Rubrica com citação de turnos (O3)
- Honeytokens + M2
- Demo ao vivo (mesmo que seja vídeo pré-gravado como plano B)

---

## 8. Riscos globais fora do código

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Ollama trava ao vivo no pitch | média | alto | vídeo pré-gravado como fallback (F.4) |
| API Anthropic fica offline | baixa | médio | Ollama como fallback via `roles.judge` swap |
| Avaliadores desistem | média | alto | recrutar 3, aceitar os 2 mais consistentes |
| Kappa < 0,6 mesmo após 2 iterações | média | crítico | reportar honestamente + análise; investidor prefere números reais a marketing |
| Prazo de disciplina bate com pitch | ? | médio | confirmar data final do INE5448 e ajustar F.5 |

---

## 9. Próximo passo concreto

**Hoje (15/09):** despachar Fase A com o comando abaixo. Nada mais.

```
/build fase A do ROADMAP_PITCH.md: implementar A.1 até A.6 na ordem, sem
avançar pra fase B enquanto o critério de pronto não estiver verde.
Cenário guia: certificate_duplicate_confused_v1. Provider primário: Ollama.
Rodar suite ao final; reportar em 1 mensagem o que ficou verde e o que
precisa da minha decisão.
```

Se você quiser rodar Fase A e a preparação da Fase E em paralelo (recrutar avaliadores + rascunhar planilha), pode disparar E.1 e E.2 já — não bloqueia A.

---

*Documento vivo. Ajustar checkpoints e sacrifícios conforme realidade. Última revisão: 15/09/2026.*
