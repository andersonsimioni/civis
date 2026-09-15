# CIVIS — Cidadão Virtual Simulado

Simulador conversacional para treinamento de atendentes de balcão em serviços registrais brasileiros contra personas geradas por LLM (cidadão confuso, usuário agressivo, fraudador), com correção automática por rubrica e supervisão humana.

**Status:** MVP funcional (fase A do [roadmap](docs/ROADMAP_PITCH.md)). Não é um produto pronto para venda ainda.
**Contexto acadêmico:** PoC APP-01, disciplina INE5448 (IA e Segurança da Informação), UFSC 2026.2.
**Autor:** Anderson Simioni Assunção — [anderson.simioni22@gmail.com](mailto:anderson.simioni22@gmail.com)

---

## Por que existe

Treinar atendentes de balcão em cartórios de registro civil hoje depende de encenação presencial: cara, esporádica, não reprodutível, e raramente cobre o caso mais perigoso — **engenharia social**, em que um fraudador usa urgência e apelo emocional para extrair dados sigilosos ou induzir procedimentos indevidos.

O CIVIS ataca esse problema com três decisões técnicas fora do padrão de "chatbot com prompt bonito":

1. **Máquina de estados finitos própria controla o roteiro da persona.** O LLM interpreta o papel, mas não decide para onde a conversa vai — a FSM decide. Isso torna cada sessão auditável e reprodutível, e reduz drasticamente contradições ao longo de dezenas de turnos.
2. **Juiz automático em modelo distinto do que interpreta a persona.** Nenhum sistema se autoavalia. Rubrica declarativa em YAML, citação obrigatória de turnos por índice, output validado por Pydantic.
3. **Estudo de concordância juiz–humano com kappa de Cohen ≥ 0,6.** A nota automática só é aceita como métrica de treino depois de validada contra 2 avaliadores humanos independentes em 30+ sessões. Sem essa validação, é ruído colorido.

---

## Arquitetura em um diagrama

```
                  ┌──────────────────────────────────────┐
                  │  Cenário YAML                        │
                  │  (persona + facts + honeytokens +    │
                  │   expected_agent_actions)            │
                  └──────────────┬───────────────────────┘
                                 │
      ┌──────────────┐    ┌──────▼──────────┐    ┌─────────────────┐
      │  Atendente   │───▶│  Session        │◀───│  FSM Engine     │
      │  (humano ou  │    │  Orchestrator   │    │  (Phase +       │
      │   pipe)      │◀───│                 │───▶│   Emotion       │
      └──────────────┘    └──────┬──────────┘    │   deterministic)│
                                 │               └─────────────────┘
                                 │
                 ┌───────────────┴────────────────┐
                 │                                │
        ┌────────▼───────────┐          ┌─────────▼────────────┐
        │  Persona Prompt    │          │  Fact Retrieval      │
        │  (FSM-hiding,      │          │  (keyword-triggered, │
        │   injection guard) │          │   selective)         │
        └────────┬───────────┘          └──────────────────────┘
                 │
        ┌────────▼───────────┐                ┌──────────────────┐
        │  LLM Provider #1   │                │  LLM Provider #2 │
        │  (persona)         │                │  (judge — MUST   │
        │  Ollama / OpenAI-  │                │   be a different │
        │  compat / Claude   │                │   catalog entry) │
        └────────┬───────────┘                └─────────▲────────┘
                 │                                      │
                 └────────┬─────────────────────────────┘
                          │
                 ┌────────▼────────────────┐
                 │  Transcript (JSON)      │
                 │  + Verdict (rubric,     │
                 │    cited turns,         │
                 │    contradiction report)│
                 └─────────────────────────┘
```

**Separações intencionais:**
- FSM ≠ LLM: o script é auditável; a linguagem, não.
- Persona ≠ Juiz: mesmo modelo (ou mesma família) nos dois papéis viola O3 e é rejeitado por Pydantic no boot.
- Instrução ≠ Dado: input do atendente vai delimitado por `<user_input>...</user_input>` no prompt, endurecendo contra prompt injection.

---

## Como rodar

### Pré-requisitos

- Python 3.12+
- [Ollama](https://ollama.com/) rodando localmente em `http://localhost:11434` (padrão de dev — API paga é opcional).
- Modelos puxados:
  ```bash
  ollama pull qwen2.5:7b-instruct-q4_K_M
  ollama pull llama3.1:8b-instruct-q4_K_M
  ```

### Setup

```bash
git clone <este-repo>
cd civis
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/Mac
pip install -e ".[dev]"
```

### Rodar uma sessão

```bash
python -m civis session --scenario certificate_duplicate_confused_v1
```

O CLI abre um REPL: você digita as falas do atendente, a persona responde. Linha vazia ou `Ctrl+Z`/`Ctrl+D` encerra a sessão e dispara o juiz. O verdict é gravado em `data/sessions/<YYYY-MM-DD_HHMMSS>/verdict.json`.

Para pipar um roteiro pré-escrito (útil em CI):

```bash
python -m civis session --scenario certificate_duplicate_confused_v1 < script.txt
```

### Rodar contra Claude como juiz

Copie o exemplo e ajuste:

```bash
cp data/configs/config.claude-judge.example.toml ~/.config/civis/config.toml
export ANTHROPIC_API_KEY="sk-ant-..."
python -m civis session --scenario ...
```

### Rodar a suite

```bash
python -m pytest -q
python -m ruff check src tests
```

---

## Métricas de sucesso

Do plano de trabalho (§5):

| Métrica | Alvo | Como medimos |
|---|---|---|
| **M1** — Concordância juiz-humano | kappa ≥ 0,6 sobre ≥ 30 sessões | Estudo de concordância, [protocolo aqui](docs/study_protocol.md) |
| **M2** — Segurança adversarial | vazamento < 5% | Bateria OWASP LLM Top 10 + honeytokens plantados |
| **M3** — Consistência factual | tendência decrescente | Detector de contradições integrado ao orchestrator |
| **M4** — Robustez operacional | recusa < 2% e latência p95 < 5s | Smoke test 30× por cenário/provider |
| **M5** — Cobertura | 3 perfis × ≥ 3 cenários | Cenários em `data/scenarios/` |

**M1 é inegociável.** Sem kappa validado, o CIVIS é uma demo bonita.

---

## Segurança e privacidade

- **Base 100% sintética.** Nomes, CPFs, RGs, endereços gerados por Faker com providers customizados que carimbam prefixo `FIC-` em todo documento. Zero risco de reidentificação (LGPD, art. 12).
- **Honeytokens.** Cenários adversariais plantam dados sigilosos rastreáveis; vazamento é detectável e mensurável.
- **Hardening de prompt.** Separação instrução/dado via delimitadores, instrução de sistema no cabeçalho e rodapé (padrão sanduíche de [Shi et al. 2024](https://arxiv.org/abs/2403.17710)), rejeição de metacomandos.
- **Modelo de ameaça declarado.** Ver `docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`, especialmente §11 (trabalhos futuros): o próprio CIVIS ataca seu juiz automático adaptando o JudgeDeceiver ao regime pointwise/rubrica.
- **Supervisão humana.** Nota automática nunca é avaliação única (goal O6). A rubrica leiga em `data/study/rubric_evaluator.md` deixa auditor humano na malha.

---

## Documentos de referência

| Documento | O quê |
|---|---|
| [`docs/Plano_de_Trabalho_CIVIS.pdf`](docs/Plano_de_Trabalho_CIVIS.pdf) | Escopo, objetivos O1–O6, metodologia (INE5448) |
| [`docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf`](docs/Analise_Critica_JudgeDeceiver_AndersonAssuncao.pdf) | Análise do artigo Shi et al. 2024 (CCS'24) — origem do diferencial de segurança |
| [`docs/ROADMAP_PITCH.md`](docs/ROADMAP_PITCH.md) | Fases A–F até o pitch de investidor em 15/12/2026 |
| [`docs/study_protocol.md`](docs/study_protocol.md) | Protocolo do estudo de concordância (M1) |
| [`data/study/rubric_evaluator.md`](data/study/rubric_evaluator.md) | Rubrica leiga, escala 0–5, 4 critérios |

---

## Contribuindo

Este é um projeto acadêmico em desenvolvimento ativo. Convenções firmes do repositório:

- Código, comentários, docstrings, testes, mensagens de commit e nomes de arquivo em **inglês**.
- Conteúdo que vai para o LLM (system prompts, descrições de critérios) em **português brasileiro**.
- Toda decisão de design não óbvia comentada em 1–2 linhas na altura do código.
- Testes antes ou junto do código, nunca depois.
- Ruff limpo e pytest verde antes de qualquer commit.

---

## Licença e uso

Definir antes do lançamento externo. Enquanto está sob avaliação acadêmica, o código é de uso restrito ao autor e à disciplina INE5448.

---

*Última revisão: 15/09/2026.*
