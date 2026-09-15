# CIVIS — Protocolo do Estudo de Concordância Juiz-Humano

**Versão:** v1.0
**Data de emissão:** 15 de setembro de 2026
**Coordenador:** Anderson Simioni Assunção
**Contato:** anderson.simioni22@gmail.com
**Aprovação ética:** não se aplica — o estudo avalia diálogos 100% sintéticos, sem envolver dados de pessoas reais nem coleta de dados dos avaliadores além do próprio julgamento anônimo.

---

## 1. Por que este estudo existe

O CIVIS é um simulador conversacional que treina atendentes de balcão em serviços registrais contra personas geradas por LLM. Ao final de cada sessão, um **juiz automático** (outro LLM) atribui notas de rubrica ao atendimento e cita os turnos exatos onde cada critério foi atendido ou violado.

Esse juiz só é confiável se, em média, ele **concordar com humanos treinados** em nível estatisticamente substancial. Sem essa validação, a nota automática vira ruído colorido: bonita para investidor, inútil para o profissional em treinamento.

Este protocolo descreve como medimos essa concordância.

## 2. Objetivo

Estimar a **concordância entre o juiz automático do CIVIS e dois avaliadores humanos independentes**, expressa pelo **kappa de Cohen** por critério de rubrica e no agregado.

**Meta declarada no plano de trabalho:** kappa ≥ 0,6 (concordância substancial, faixa de Landis & Koch 1977) sobre ≥ 30 sessões.

**Interpretação da faixa (para justificar o que é "substancial"):**

| Kappa | Interpretação |
|---|---|
| < 0,00 | pior que acaso |
| 0,00 – 0,20 | leve |
| 0,21 – 0,40 | razoável |
| 0,41 – 0,60 | moderada |
| **0,61 – 0,80** | **substancial** ← alvo |
| 0,81 – 1,00 | quase perfeita |

## 3. Escopo

- **Sessões avaliadas:** ≥ 30. Distribuídas em 3 perfis de persona (confusa, agressiva, fraudadora) × ao menos 2 cenários por perfil.
- **Avaliadores humanos:** 2, independentes, sem visibilidade dos escores um do outro nem do juiz automático até o término da coleta.
- **Sessões que estão fora do escopo:** ataques adversariais (avaliados na bateria de segurança M2, não aqui).
- **Idioma:** todas as transcrições e a rubrica em português brasileiro.

## 4. Rubrica

Idêntica em critérios à rubrica do juiz automático, redigida sem termos técnicos de LLM para não enviesar avaliadores leigos em IA. Ver arquivo separado: `data/study/rubric_evaluator.md`.

**Quatro critérios, escala 0–5:**

1. **Verificação de fatos** — o atendente confirmou a identidade da pessoa antes de qualquer ação sensível?
2. **Proteção de dados** — o atendente evitou vazar dados sigilosos do cenário?
3. **Aderência ao protocolo** — o atendente seguiu o procedimento esperado?
4. **Comunicação** — o atendente foi claro, respeitoso e didático?

## 5. Procedimento por avaliador

Cada avaliador recebe:

1. Um **link/pasta compartilhada** com as transcrições numeradas (`session_001.md` a `session_030.md`, formato conversacional simples).
2. Uma **cópia própria** do `data/study/evaluator_template.csv`, já preenchida com as colunas `session_id` e `criterion`.
3. O **arquivo de rubrica** (`rubric_evaluator.md`) para consulta contínua.

**Fluxo esperado por sessão (~30 minutos cada):**

1. Ler a transcrição na íntegra sem consultar a rubrica (impressão global primeiro).
2. Reler consultando a rubrica, critério a critério.
3. Atribuir score 0–5 por critério e escrever uma nota qualitativa curta (1 linha) justificando o score.
4. Preencher a coluna `evaluated_at` com o timestamp ISO 8601.
5. Nunca voltar em sessões já avaliadas (a rubrica pode ser refinada mentalmente pela experiência, mas cada linha final é a impressão do momento).

**Compromisso total de tempo por avaliador:** 30 sessões × 30 min = **~15 horas**, distribuídas em janela flexível (sugestão: 5 sessões/semana durante 6 semanas).

## 6. Regras de independência

Isto é o que separa o estudo de uma revisão em pares informal:

- Avaliadores **não conversam sobre sessões específicas** durante a coleta.
- Avaliadores **não veem** o score do outro avaliador nem do juiz automático até o término.
- O coordenador consolida os 3 conjuntos de escores apenas após o último dia da coleta.
- Se um avaliador tiver dúvida procedimental (não sobre uma sessão), pergunta ao coordenador, que responde a ambos em canal comum.

## 7. Perfil desejado do avaliador

- Familiaridade com atendimento ao público, direito registral, ou treinamento de agentes públicos (bônus, não obrigatório).
- Leitura confortável em português brasileiro formal.
- Disponibilidade de ~15 horas em janela de até 8 semanas.
- Sem conflito de interesse comercial com o CIVIS.
- Sem viés de "torcida" — o objetivo do avaliador é discordar do juiz automático quando ele errar, não confirmá-lo.

**Sugestão de recrutamento:** 2 colegas do curso INE5448 ou de disciplinas correlatas, ou 1 colega + 1 servidor público com experiência de balcão. Recrutar 3 e usar as 2 avaliações mais consistentes (kappa avaliador-avaliador ≥ 0,5) se um desistir.

## 8. Aspectos éticos e privacidade

- **Dados sintéticos:** todas as transcrições avaliadas foram geradas contra personas fictícias (nomes, CPFs, RGs marcados com prefixo `FIC-`). Nenhuma pessoa real é representada. Base construída conforme LGPD (§6 do plano de trabalho).
- **Dados dos avaliadores:** apenas o nome (ou pseudônimo, se preferirem) para agregação. Nenhum dado sensível coletado. Escores são armazenados anonimamente (`avaliador_1`, `avaliador_2`).
- **Consentimento:** avaliador declara ciência deste protocolo antes de iniciar (assinatura eletrônica em e-mail é suficiente para este piloto acadêmico).
- **Direito de saída:** avaliador pode encerrar a qualquer momento; escores parciais não são utilizados sem consentimento explícito.

## 9. Cálculo do kappa

Executado por `scripts/compute_kappa.py` (implementação verificada com dados sintéticos e casos-limite documentados no próprio script).

**Kappa reportado:**

- **Por critério** (4 valores).
- **Agregado** (média ponderada por N de sessões).
- **Avaliador humano × juiz automático** (foco do estudo — 2 comparações: juiz vs avaliador_1 e juiz vs avaliador_2).
- **Avaliador humano × avaliador humano** (sanity check — se estiver baixo, o problema é a rubrica, não o juiz).

**Ponderação:** quadratic weighted kappa por padrão. Justificativa: os escores são ordinais (0–5), e discordância de 1 ponto é substancialmente menos grave que discordância de 4 pontos — quadratic captura essa nuance. Linear weighted e unweighted também são reportados para transparência.

**Intervalo de confiança:** 95% via bootstrap com 1 000 amostras. Necessário para o pitch — investidor sério pergunta o IC.

## 10. Cronograma do estudo

Alinhado com a Fase E do `docs/ROADMAP_PITCH.md`:

| Data-limite | Marco |
|---|---|
| **06/10/2026** | Rubrica e template CSV finalizados, avaliadores recrutados |
| **13/10/2026** | Sessão-piloto (1 sessão avaliada por ambos, calibração da rubrica) |
| **03/11/2026** | Primeiras 10 sessões avaliadas — checkpoint intermediário (§11) |
| **08/12/2026** | 30 sessões completas, kappa final calculado |
| **15/12/2026** | Resultado no deck de pitch |

## 11. Checkpoint intermediário (crítico)

Em 03/11 rodar `compute_kappa.py` sobre as primeiras 10 sessões:

- **Kappa ≥ 0,55:** seguir sem mudanças, com confiança de que o alvo final ≥ 0,6 é factível.
- **Kappa 0,4 – 0,55:** analisar discordâncias por critério, ajustar rubrica se um critério estiver puxando pra baixo. Rerun das 10 sessões existentes com rubrica ajustada.
- **Kappa < 0,4:** parar coleta. Problema estrutural — ou a rubrica está ambígua, ou o juiz automático está muito mal calibrado. Corrigir raiz antes de gastar as 20 sessões restantes.

Este checkpoint é o que protege o pitch: se descobrimos problema em 3/11, sobra 5 semanas para corrigir. Se descobrimos em 8/12, o pitch acontece com kappa parcial + análise honesta do por quê — pior cenário, mas ainda apresentável.

## 12. Uso dos resultados

- **Relatório final da disciplina INE5448** (docente: Prof. Ricardo Felipe Custódio) — resultado quantitativo do M1, discussão de limitações, cumprimento do objetivo O5.
- **Deck de pitch de investidor** (15/12/2026) — kappa como prova de que a nota automática do CIVIS é validada e não é ruído.
- **Publicação futura opcional** — se o kappa for substancial e o método for reproduzível, submeter para venue nacional (ex.: SBSeg ou SBIE).

Todos os dados brutos (transcrições sintéticas, CSVs de avaliação, script de cálculo) serão publicados junto com o relatório para reprodutibilidade — em linha com o goal O6.

## 13. Riscos declarados

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Kappa final < 0,6 | média | Checkpoint intermediário (§11); reportar honestamente se não bater |
| Avaliador desiste no meio | média | Recrutar 3 desde o início, usar 2 mais consistentes |
| Discordância sistemática em 1 critério | média-alta | Sessão-piloto (13/10) explicitamente para calibrar rubrica antes da coleta em massa |
| Viés de ordem (sessões finais avaliadas com mais rigor que iniciais) | baixa | Aleatorização da ordem entre avaliadores (avaliador 1 começa por session_001, avaliador 2 por session_016) |
| Coordenador (Anderson) também sendo avaliador introduz viés | alta se aplicável | Anderson **não avalia** — apenas coordena e roda as sessões. Ambos os avaliadores são externos |

---

*Documento vivo — última revisão: 15/09/2026. Ajustar §10 e §11 conforme calendário real das etapas anteriores do roadmap.*
