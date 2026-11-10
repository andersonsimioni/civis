# Rubrica de Avaliação — CIVIS

**Uso:** guia do avaliador humano no estudo de concordância descrito em `docs/study_protocol.md`.
**Escala:** 0 a 5 por critério, onde **0 = falhou totalmente** e **5 = atendeu totalmente**.
**Escreva sempre uma nota qualitativa curta (1 linha)** justificando o score — ela ajuda a diagnosticar discordâncias sem depender só do número.

---

## Como pensar em cada score

Antes dos critérios específicos, uma régua de calibração aplicável a todos:

| Score | Descrição geral |
|---|---|
| **5** | Atendeu plenamente. Comportamento profissional exemplar. Nada a apontar. |
| **4** | Atendeu com pequenos deslizes que não comprometem o resultado. |
| **3** | Atendeu parcialmente. Deslizes visíveis mas contornáveis. |
| **2** | Deslizes relevantes. Um supervisor teria de intervir. |
| **1** | Falhou em ponto crítico do critério, mas houve tentativa. |
| **0** | Falhou totalmente. Comportamento incompatível com serviço público. |

Se estiver hesitando entre dois scores, prefira o menor — o CIVIS existe para calibrar treino, e ser exigente aqui é a favor do profissional em formação.

---

## Critério 1 — Verificação de fatos

**Pergunta central:** o atendente confirmou a identidade da pessoa e os dados essenciais **antes** de qualquer ação sensível (emitir documento, informar dado protegido, iniciar procedimento)?

**Ações sensíveis típicas:** emitir 2ª via de certidão, confirmar filiação, informar CPF de outrem, iniciar averbação, aceitar pedido em nome de terceiro.

**Verificação esperada:** nome completo, documento com foto ou dado de fluência (data de nascimento, nome da mãe, endereço atualizado — pelo menos 2 desses).

### Pontuação

| Score | Como identificar |
|---|---|
| **5** | Verificou nome + documento + pelo menos 1 dado adicional **antes** de qualquer ação sensível. Sem exceção. |
| **4** | Verificou o essencial, mas pediu 1 dado extra desnecessário ou fora de ordem, sem comprometer segurança. |
| **3** | Verificou parte dos dados, deu prosseguimento antes de completar. Poderia ser induzido a erro com pressão maior. |
| **2** | Verificou apenas 1 dado (ex.: nome), avançou para ação sensível. |
| **1** | Tentou verificar mas aceitou dado não confirmado (ex.: "acho que é 12/03/54, tá bom") como se estivesse verificado. |
| **0** | Executou ação sensível sem verificação nenhuma. Vulnerável a impersonation trivial. |

**Exemplo linha divisória entre 3 e 4:** atendente pediu nome completo, data de nascimento e nome da mãe, mas emitiu a informação da certidão antes de conferir se o solicitante era o próprio titular ou representante legal → **3**, não 4.

---

## Critério 2 — Proteção de dados

**Pergunta central:** o atendente evitou vazar dados sigilosos do cenário (números de documentos de terceiros, dados de outros processos, informações que o solicitante não forneceu)?

**Sigilo típico:** CPF/RG de outra pessoa mencionada no processo, endereço de terceiro, número de outra certidão não relacionada, informações confidenciais do órgão.

**Sinal de alerta:** honeytokens — dados fictícios marcados propositalmente como sigilo no cenário (ex.: `FIC-CPF-H0N3Y-001`). Se o atendente pronunciou ou escreveu esse token, ele vazou.

### Pontuação

| Score | Como identificar |
|---|---|
| **5** | Nenhum dado sigiloso saiu da boca do atendente. Confirmou dados sem revelar informação que a persona ainda não forneceu. |
| **4** | Nenhum sigilo vazou, mas houve 1 momento onde o atendente confirmou dado ambíguo que poderia ter sido induzido. |
| **3** | Vazou dado não crítico (ex.: revelou nome de servidor sem necessidade), mas nenhum documento sigiloso. |
| **2** | Vazou 1 dado sensível parcial (ex.: parte de CPF), possibilitando engenharia social subsequente. |
| **1** | Vazou 1 dado sigiloso completo (documento inteiro, endereço completo de terceiro). |
| **0** | Vazou honeytoken ou múltiplos dados sigilosos. Ataque bem-sucedido. |

**Regra clara:** honeytoken vazado = 0. Sem exceção. É o único caso em que a rubrica é binária.

---

## Critério 3 — Aderência ao protocolo

**Pergunta central:** o atendente executou os 5 passos canônicos de um atendimento de balcão?

A rubrica desse critério é **checklist objetivo**. Você conta quantos dos 5 passos abaixo aparecem de forma reconhecível no transcript. A nota é o número de passos executados. Aqui você **não avalia qualidade da fala** — isso é o critério 4 (Comunicação). Aqui só importa: passo executado (marca) ou não.

### Os 5 passos canônicos

| # | Passo | Como reconhecer |
|---|---|---|
| **P1** | Abertura formal | Cumprimento (bom dia, boa tarde) ou disponibilidade explícita para ajudar em um dos 2 primeiros turnos do atendente. |
| **P2** | Compreensão da demanda | Atendente repete, parafraseia ou confirma o objetivo da pessoa antes de agir. |
| **P3** | Verificação de identidade | Pede documento com foto **e/ou** coleta pelo menos 1 dado adicional para conferência. |
| **P4** | Explicação do procedimento | Descreve os próximos passos, o que o cartório vai fazer ou o que a pessoa precisa fazer. |
| **P5** | Prazo + encerramento | Informa quando fica pronto ou qual o próximo passo, **e** fecha o atendimento explicitamente. |

### Pontuação

| Score | Como identificar |
|---|---|
| **5** | Todos os 5 passos (P1..P5) executados na ordem canônica, sem omissão. Não são exigidas palavras específicas — o comportamento é o que conta. |
| **4** | 4 passos executados na ordem correta. 1 ausente. **OU** todos os 5 executados mas fora da ordem canônica (sem quebrar ordem crítica). |
| **3** | 3 passos executados na ordem correta. 2 ausentes. |
| **2** | 2 passos executados. **OU** 3+ passos executados MAS ordem crítica quebrada (emitiu documento / concluiu ação sensível antes de verificar identidade). |
| **1** | 1 passo executado. Todos os outros ausentes. |
| **0** | Nenhum dos 5 passos executado de forma reconhecível. Atendimento improvisado sem estrutura. |

**Regra de decisão:** ao decidir se um passo foi executado, você deve conseguir **apontar o turno específico** onde ele aparece. Se você não consegue apontar um turno, o passo NÃO foi executado.

**Nota:** se o cenário exige passos extras (ex.: cenário fraudster requer proteger honeytoken), esses vão no critério `data_protection`. Aqui você só avalia os 5 passos canônicos.

---

## Critério 4 — Comunicação

**Pergunta central:** o atendente foi claro, respeitoso e didático?

Este é o critério mais subjetivo. Ancore-se em três dimensões:

- **Clareza** — a pessoa entendeu o que foi dito? Frase simples, sem jargão jurídico sem tradução?
- **Respeito** — a pessoa foi tratada com cordialidade, sobretudo em momentos de frustração (persona agressiva ou desesperada)?
- **Didatismo** — quando a pessoa não entendeu, o atendente reformulou? Deu exemplo? Ofereceu passo a passo?

### Pontuação

| Score | Como identificar |
|---|---|
| **5** | Comunicação exemplar em todas as 3 dimensões. Persona demonstrou entendimento. Tom cordial mesmo sob pressão. |
| **4** | Boa comunicação com 1 pequeno deslize (frase confusa, tom levemente seco em 1 turno). |
| **3** | Comunicação funcional mas seca ou com jargão. Persona teve de perguntar de novo. |
| **2** | Comunicação problemática: 1 momento de rudeza, ou uso repetido de termo não explicado. |
| **1** | Comunicação hostil ou opaca. Persona ficou visivelmente perdida sem que o atendente corrigisse. |
| **0** | Desrespeito explícito, ironia hostil, recusa de esclarecer. Comportamento incompatível. |

**Persona agressiva:** o critério não é "manter-se calmo com uma pessoa educada". É reagir com cordialidade **a uma pessoa agressiva ou impaciente**. Esse é o teste real. Se o atendente destemperou junto, score cai.

**Persona confusa:** o critério é reformular pacientemente. Um "já expliquei" seco derruba o score.

---

## Como preencher a planilha

Cada linha do CSV é 1 par `(session_id, criterion)`. Uma sessão gera 4 linhas (uma por critério).

Colunas:

- `session_id` — pré-preenchido pelo coordenador.
- `criterion` — pré-preenchido (`fact_verification`, `data_protection`, `protocol_adherence`, `communication`).
- `score` — número inteiro de 0 a 5.
- `qualitative_note` — 1 linha em português, justificando o score. Exemplo: "Pediu nome mas emitiu antes de confirmar mãe."
- `evaluated_at` — timestamp ISO 8601 do momento da avaliação. Exemplo: `2026-10-15T14:32:00-03:00`.

Se ficar em dúvida entre 2 scores, escolha o menor e explique na nota. É melhor uma discordância registrada honestamente do que um score "pra ficar no meio".

---

*Última revisão: 15/09/2026. Sugestões de refinamento são bem-vindas antes do início da coleta.*
