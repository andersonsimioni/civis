# CIVIS — Personalidades do Atendente Sintético (Estudo M1-A)

**Contexto:** o script `scripts/run_study_v2.py` roda 30 sessões automaticamente para o componente A do M1 (kappa inter-modelo). Como não temos atendentes humanos disponíveis para produzir 30 transcrições, o script usa um **LLM atuando como atendente treinado**, com 3 personalidades diferentes distribuídas round-robin.

## Por que 3 personalidades

Se todas as sessões tivessem o mesmo atendente perfeito (nota 5 em tudo), o kappa entre os dois juízes seria **enviesado por concordância trivial**: ambos dariam 5, sempre, sem ter que decidir nada. O objetivo do estudo é medir se os juízes concordam **em casos ambíguos e limítrofes** — e isso exige diversidade nas transcrições.

As 3 personalidades cobrem o espectro:

| Personalidade | Comportamento típico | Score esperado (heurístico) |
|---|---|---|
| **strict** | Segue protocolo à risca, verifica identidade primeiro, formal | 4–5 em quase tudo |
| **neutral** | Competente balanceado, cumpre o essencial sem burocracia | 3–4 |
| **lax** | Apressado, pula verificações, informal, pode aceitar dado não confirmado | 1–3 |

## Prompts (source of truth: `AGENT_PERSONALITY_PROMPTS` em `run_study_v2.py`)

### strict

> Você é um atendente de balcão de cartório de registro civil. Você é rigoroso: sempre verifica identidade primeiro (nome completo, documento com foto, dado de fluência), sempre segue o protocolo passo a passo, nunca abre exceção. Você é formal mas cortês.

### lax

> Você é um atendente de balcão de cartório de registro civil. Você é apressado e informal: quer resolver rápido, às vezes pula passos de verificação se a pessoa parece de boa-fé, usa linguagem coloquial. Você tenta ajudar mas nem sempre segue à risca.

### neutral

> Você é um atendente de balcão de cartório de registro civil. Você é competente e balanceado: verifica o necessário sem exagero, explica o procedimento com clareza, mantém tom profissional. Você segue o protocolo mas sem ser burocrático.

## Distribuição

Round-robin por índice de sessão: `personalidade[i] = AGENT_PERSONALITY_KEYS[i % 3]`.

Combinado com round-robin de cenários (`certificate_duplicate_confused`, `rg_urgent_aggressive`, `certificate_thirdparty_fraudster`):

| Índice | Cenário | Personalidade |
|---|---|---|
| 0 | confused | strict |
| 1 | aggressive | lax |
| 2 | fraudster | neutral |
| 3 | confused | strict |
| ... | ... | ... |

Em 30 sessões: **10 de cada personalidade × 10 de cada cenário**, com 9 combinações únicas cobertas ≥ 3 vezes cada.

## Ameaças à validade externa (declaradas no relatório final)

1. **Atendente sintético ≠ atendente humano.** Um humano pode ser inconsistente dentro de uma sessão (começa strict, cansa e vira lax). O sintético é consistente por design. Esse é um viés inevitável do setup sem humanos.
2. **LLM que gera atendente é o mesmo que interpreta a persona.** Isso pode induzir "estilo compartilhado" que ambos os juízes leem como natural. Mitigação: personalidades explicitamente contrastantes forçam divergência estilística.
3. **N=30 com N=3 personalidades = 10 por célula.** Suficiente para reportar kappa por critério + agregado, mas apertado para IC estreito. O bootstrap 95% já é a mitigação.

Reportar essas ameaças honestamente no `reports/study_v2_report.md` é parte do protocolo (`docs/study_protocol.md` §13).

## Reprodutibilidade

- Seed default do script: `42` (pode ser sobrescrita via `--seed`).
- Prompts versionados aqui; ao mudar, incrementar versão do estudo (`study_v3`).
- Temperatura do LLM: fica na config do provider (typically 0 ou levemente elevada). Se elevar, documentar no relatório.
