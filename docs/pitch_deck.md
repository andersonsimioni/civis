# CIVIS — Deck de Pitch para Investidor (rascunho)

**Alvo:** 15 de dezembro de 2026 · 10 minutos de apresentação + 10 de perguntas
**Autor:** Anderson Simioni Assunção
**Status:** ⚠️ RASCUNHO — placeholders `[X]` serão preenchidos quando C e E fecharem (kappa real, ASR real, latência real).

> **Instrução para futuro-eu:** este é o esqueleto verbal. Ao converter para slides visuais (Slidev/Keynote/Google Slides), 1 seção `##` = 1 slide. Copy final deve caber em 60 palavras por slide. Diagramas ASCII viram figuras vetoriais. Placeholders `[X]` são o único ponto onde números "fingidos" aparecem — não apresentar com eles preenchidos por chute.

---

## Slide 1 — Capa

**CIVIS**
Cidadão Virtual Simulado

Treino automatizado de atendentes de balcão em serviços públicos,
com validação estatística de nota automática e prova de segurança
adversarial contra o próprio avaliador.

*Anderson Simioni Assunção · UFSC INE5448 · Dezembro/2026*

---

## Slide 2 — O problema

**Treinamento de balcão em cartórios brasileiros hoje:**

- Caro (encenação presencial exige facilitador + sala + agenda)
- Esporádico (raramente cobre um mês inteiro sem gap)
- Não reprodutível (cada facilitador improvisa cenário próprio)
- **Falha justamente no caso mais grave: engenharia social**

Fraudador não avisa que é fraudador. Ele chega com urgência,
apelo emocional e história plausível — o mesmo padrão que
atendentes só aprendem a reconhecer errando na vida real.

**14 mil cartórios de registro civil no Brasil.** Todos precisam
treinar. Poucos treinam bem.

---

## Slide 3 — A solução

**CIVIS: simulador conversacional com correção automática.**

Atendente conversa por chat contra uma persona controlada por LLM.
Ao final, um segundo LLM avalia por rubrica declarativa, citando
os turnos exatos onde acertou ou falhou.

Três perfis:
- Cidadão confuso (dificuldade com burocracia)
- Usuário agressivo (impaciência real)
- Fraudador (engenharia social ativa, com honeytokens plantados)

Custa por sessão o que uma encenação presencial custa por turma.
Roda 24/7. Registra tudo. Cospe métrica quantitativa.

---

## Slide 4 — Mercado

**Ancoragem inicial: registro civil brasileiro.**

- ~14 000 cartórios de RC no Brasil (dado ANOREG)
- Todos com obrigação de treinamento contínuo (LGPD + Provimento CNJ 100/2020)
- Ticket médio de treinamento presencial: R$ 500–2 000 por atendente/ano

**Expansão natural:**
- Órgãos públicos com balcão (INSS, DETRAN, cartórios de imóveis, cartórios de notas)
- Bancos e cooperativas (KYC + antifraude no atendimento presencial)
- Escolas técnicas de administração pública

Total addressable market conservador para o Brasil apenas:
**R$ [X] milhões/ano** (a preencher com pesquisa de campo).

---

## Slide 5 — Tecnologia (o que diferencia)

Três decisões técnicas fora do padrão de "chatbot com prompt bonito":

**1. Máquina de estados própria controla o roteiro.**
LLM interpreta o papel; a FSM decide para onde a conversa vai.
Cada sessão é auditável e reprodutível — investigador consegue
saber exatamente por que a persona ficou frustrada no turno 5.

**2. Juiz automático em modelo distinto.**
Pydantic bloqueia inicialização se `persona == judge`. Nenhum
sistema se autoavalia. Rubrica declarativa em YAML, citação
obrigatória de turnos por índice, output validado.

**3. Segurança adversarial embutida.**
Bateria OWASP LLM Top 10 rodada contra o próprio sistema;
honeytokens plantados nos cenários; **JudgeDeceiver adaptado
ao regime pointwise/rubrica** (vetor de ataque inédito — nossa
contribuição científica).

---

## Slide 6 — Diferencial competitivo defensável

**"Simuladores conversacionais existem. O que ninguém fez ainda:"**

Testar se o próprio juiz automático pode ser manipulado pela
persona que ele está avaliando.

Nós fazemos, medimos e reportamos.

**Base:** Shi et al. 2024 (CCS'24) formalizou o ataque JudgeDeceiver
no regime *pairwise* (escolher entre respostas concorrentes).
Nosso juiz é *pointwise* (nota por rubrica sobre uma resposta única).

O ataque original **não tem análogo nesse regime** —
identificamos, adaptamos, executamos e medimos resistência.

Resultado: **[ASR = ?%] contra o juiz do CIVIS**.
Nenhum simulador comercial no mercado reporta essa métrica.

---

## Slide 7 — Evidências (métricas)

| Métrica | Alvo | **Real** |
|---|---|---|
| Kappa juiz-humano (M1) | ≥ 0,6 | **[X]** (IC 95% [X, X]) |
| Vazamento adversarial (M2) | < 5% | **[X]%** |
| ASR contra juiz (JudgeDeceiver-pw) | reportar | **[X]%** |
| Latência p95 por turno (M4) | < 5s | **[X]s** |
| Contradições / 100 turnos (M3) | decrescente | **[X]** |
| Cobertura de cenários (M5) | 3×3 | **[X]** cenários |

**Metodologia inteira publicada** — não é opinião, é reprodutível.

Bootstrap 95% CI no kappa. Dois avaliadores humanos independentes.
Rubrica declarativa versionada. Suíte de testes verde em CI.

---

## Slide 8 — Demo ao vivo (3 minutos)

*[Reservar 3 minutos aqui. Roteiro:]*

1. Abrir CLI: `python -m civis session --scenario certificate_thirdparty_fraudster_v1`
2. Conversar 8 turnos com a persona fraudadora (com pressão emocional realista).
3. Encerrar sessão (Ctrl+Z).
4. Mostrar o `verdict.json` gerado: nota por critério + turnos citados literalmente.
5. Abrir painel Streamlit: transcript à esquerda, rubrica com highlight à direita.
6. Mostrar telemetria: latência p95, contradições detectadas.

**Plano B (se Ollama travar ao vivo):**
Vídeo pré-gravado da mesma sessão, gerado durante a Fase D. Não interromper — pular.

---

## Slide 9 — Como comparamos

|   | Simuladores atuais | **CIVIS** |
|---|---|---|
| Roteiro | LLM decide | FSM auditável |
| Correção | LLM opina | Rubrica declarativa + citação de turno |
| Validação | "achamos que funciona" | **Kappa ≥ 0,6 com IC** |
| Segurança | não reportada | Bateria OWASP + JudgeDeceiver-pw |
| Reprodutibilidade | prompts secretos | Seeds versionadas, código aberto |
| LGPD | dados reais anonimizados | 100% sintético, prefixo `FIC-` |

---

## Slide 10 — Roadmap

**Já entregue (setembro–dezembro 2026):**
- ✅ MVP funcional em Ollama e Claude (Fase A)
- ✅ Juiz com rubrica completa + citação validada (Fase B)
- ✅ Bateria de segurança + JudgeDeceiver-pw (Fase C)
- ✅ Interface web + telemetria (Fase D)
- ✅ Estudo de concordância publicado (Fase E)

**6 meses (jan–jun 2027):**
- Piloto pago em 3 cartórios de SC + relatório de eficácia
- Multi-tenant + gestão de turmas
- Modo de voz full-duplex (transcrição + TTS em tempo real)

**12 meses (2027–2028):**
- Expansão para outros órgãos com balcão (INSS, DETRAN)
- Marketplace de cenários (comunidade contribuindo)
- Certificação reconhecida pelo CNJ

---

## Slide 11 — Time

**Anderson Simioni Assunção**
Autor único do projeto até aqui. Aluno UFSC INE5448.
- Domínio técnico: Python, LLMs, arquitetura de sistemas, segurança
- Trilha acadêmica: Trilha 3 (Aplicações Transversais), catálogo APP-01
- Orientação: [orientador da disciplina/estágio, se aplicável]

**Buscando co-founder técnico** para escalar de PoC acadêmica
para produto piloto. Perfil ideal: engenharia sênior + relacionamento
com cartorial/setor público.

**Advisors mapeados** (a confirmar): [contatos internos UFSC + ANOREG-SC].

---

## Slide 12 — Perguntas prováveis (nota do apresentador, não do slide)

**"E se o LLM erra?"**
Por isso o kappa. A nota automática não é entregue como verdade —
é uma opinião estatisticamente validada, e a arquitetura assume
supervisão humana amostral em produção.

**"E se alguém quebrar o juiz?"**
Reportamos. O JudgeDeceiver-pw é um ataque real e nós medimos a
resistência. ASR de X% significa que N% dos ataques passam — e
isso é dado quantitativo, não retórica.

**"E as alucinações?"**
Rubrica exige citação literal de turno. Nosso validador rejeita
qualquer verdict com excerpt que não seja substring da transcrição.
Retry automático quando detecta.

**"Custo por sessão?"**
Com Claude Sonnet: ~R$ [X] por sessão (a medir na Fase D).
Com Ollama local: energia + hardware, escalável sem custo marginal.

**"LGPD?"**
100% sintético, prefixo `FIC-` em todo documento. Nenhuma pessoa
real representada. Auditoria trivial.

---

## Slide 13 — O ask

Estamos abertos a conversar sobre três formatos:

**1. Pré-semente (R$ [X])** — 12 meses de runway para:
- Contratar 1 engenheiro sênior + 1 pesquisador de campo
- Piloto pago em 3 cartórios de SC (revenue validation)
- Certificação técnica com órgão registral

**2. Grant acadêmico + parceria** — para publicação do JudgeDeceiver-pw
em venue A/A* e uso do CIVIS como plataforma de pesquisa.

**3. Advisor com equity vestido** — quem conhece cartorial ou setor
público e quer construir junto.

**Contato:** anderson.simioni22@gmail.com

---

## Apêndice A — Diagrama técnico (para investidor técnico)

```
[Diagrama de arquitetura completo — copiar do README.md,
 versão limpa em PDF para o apêndice.]
```

---

## Apêndice B — Referências

- Shi, J. et al. (2024). *Optimization-based Prompt Injection Attack to LLM-as-a-Judge.* CCS'24.
- Análise crítica completa: `docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`
- Landis & Koch (1977). *The measurement of observer agreement for categorical data.* Biometrics.
- OWASP LLM Top 10 (2025).
- CNJ Provimento 100/2020.
- ANOREG — dados de cartórios de RC.

---

*Rascunho v0. Última revisão: 15/09/2026. Recolher métricas reais nas Fases C e E antes de apresentar.*
