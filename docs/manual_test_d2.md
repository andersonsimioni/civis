# Checklist manual — D.2 painel de correção lado a lado

Streamlit `AppTest` cobre a lógica de estado e a árvore de widgets, mas
não faz screenshot nem checa o estilo renderizado. Este checklist é o
que o Anderson roda a olho antes do pitch para garantir que o painel
funciona visualmente. **Regra de ouro:** hesitou em qualquer item, mais
polish.

## Setup

```bash
# 1. Garante sessões demo em data/sessions/
python scripts/generate_demo_sessions.py

# 2. Sobe o app
streamlit run src/civis/web/app.py

# 3. Abre no navegador
http://localhost:8501
```

O default de página é "Nova sessão". Clique em **Sessões passadas** no
menu lateral para começar o teste.

## Lista + filtros

- [ ] A lista aparece com 5 linhas (as sessões demo).
- [ ] Cada linha mostra: id da sessão · cenário em pt-BR · data ·
      turnos · nota média · sinais (`⚠️ contradição`, `🕵️ vazamento`) ·
      botão "Abrir".
- [ ] `demo_fraudster_leak_v1` marca "🕵️ vazamento".
- [ ] `demo_aggressive_mixed_v1` marca "⚠️ contradição".
- [ ] Filtro por cenário (multiselect à esquerda) — escolha
      "certificate_thirdparty_fraudster_v1"; a lista cai para 2 linhas.
- [ ] Filtro de nota (slider) `min=4.5, max=5.0` deixa apenas 2 linhas
      (o "confused good" e o "fraudster defended").
- [ ] Filtro "Somente com" contradições deixa 1 linha.
- [ ] Filtro "Somente com" vazamento deixa 1 linha.

## Drill-down (D.2)

Clique em "Abrir" na sessão `demo_fraudster_leak_v1`.

- [ ] A página muda: o header mostra o id, o cenário e a data.
- [ ] Ícone de "Voltar" no canto direito.
- [ ] Coluna esquerda (60%): o transcript com 10 turnos alternados.
- [ ] Bolha do atendente tem fundo azul-claro; do cidadão, fundo branco.
- [ ] Cada bolha tem cabeçalho: ícone + "Atendente"/"Cidadão" · turno N ·
      data legível.
- [ ] Coluna direita (40%): "Resumo do juiz" no topo com o overall.
- [ ] Abaixo, "Critérios" com 4 cards abertos por padrão.
- [ ] Cada card tem badge de nota colorido (0-2 vermelho, 3 amarelo, 4-5
      verde), rótulo em pt-BR, rationale, quote em itálico, e um botão
      "↗ Ver turno N".

## Interação de citação (o vende!)

- [ ] Clique no botão "↗ Ver turno 4" do critério "Proteção de dados".
- [ ] O turno 4 (`Achei aqui. Processo FIC-CASE-H0N3Y-CERT-004…`) recebe
      fundo amarelo destacado no transcript à esquerda.
- [ ] O navegador rola até o turno destacado (efeito `scrollIntoView`).
- [ ] Depois de ~2,5 s, o destaque diminui (efeito de flash).
- [ ] Clicando em outra citação, o destaque anterior some e o novo turno
      é marcado.

## Sinais laterais (contradições + honeytokens)

- [ ] Abaixo dos critérios, dois cards colapsáveis:
      "⚠️ Contradições detectadas (0)" (verde-friendly) e
      "🕵️ Vazamento de honeytoken (2)" (aberto por padrão pelo número > 0).
- [ ] O card de vazamento lista os dois honeytokens com turno, chave e
      contexto.
- [ ] Volte para a lista e abra `demo_confused_good_v1`: os dois cards
      mostram estado "verde" (0 e 0) com copy positiva.

## Régua final (o teste sujo mas honesto)

- [ ] Olhando as 4 páginas, você sente "isso passaria numa apresentação
      a investidor de VC" ou "parece TCC"?
- [ ] Se hesitou, mais polish (T7).

## O que sabidamente NÃO passa aqui

- Screenshot automático (Streamlit não oferece pipeline de testes visuais).
- Verificação em runtime real de JavaScript executado no navegador
  (`AppTest` não abre navegador; a asserção fica no CSS injetado).
- Layout responsivo abaixo de 1024 px (o wide layout comprime as duas
  colunas em uma coluna estreita — aceitável para demo em telão, mas
  não substitui uma media query dedicada).
