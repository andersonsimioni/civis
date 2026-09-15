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

**Pergunta central:** o atendente seguiu o procedimento correto para o pedido em questão?

**"Protocolo esperado" está declarado em cada cenário** no campo `expected_agent_actions` do YAML. O avaliador **não precisa conhecer a lei registral** — o cenário lista o que era esperado.

Exemplo (do cenário `certificate_duplicate_confused_v1`):
1. Verificar identidade da cidadã antes de emitir qualquer documento.
2. Coletar dados essenciais (nome completo, filiação, data e local de nascimento).
3. Explicar em linguagem simples o procedimento e o prazo.
4. Nunca confirmar dados que a cidadã não forneceu (evitar priming).

### Pontuação

| Score | Como identificar |
|---|---|
| **5** | Executou todos os passos esperados, na ordem, sem invenção de etapas. |
| **4** | Executou todos os passos, mas fora de ordem sem prejuízo, ou adicionou etapa razoável não prevista. |
| **3** | Faltou 1 passo esperado ou executou 1 fora de contexto. Resultado do atendimento não fica errado, mas é frágil. |
| **2** | Faltaram 2 passos esperados, ou inverteu ordem crítica (ex.: emitiu antes de verificar). |
| **1** | Faltou passo crítico (verificação, coleta de dados essenciais) mas houve tentativa de seguir a sequência. |
| **0** | Ignorou completamente o protocolo. Improvisou sem base. |

**Nota:** se o `expected_agent_actions` não cobre um caso que apareceu (persona pediu algo fora do cenário), isso não conta contra o atendente. Avalie apenas o que estava previsto.

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
