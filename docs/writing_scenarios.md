# Guia de autoria de cenários

Um cenário CIVIS é um arquivo YAML em `data/scenarios/`. Cada arquivo
descreve uma situação de balcão: quem é a persona, o que ela sabe, o
que o atendente deveria fazer, quais ações clicáveis existem e quais
armadilhas de segurança (honeytokens) foram plantadas.

Este guia mostra a estrutura completa, o que é obrigatório, o que é
opcional e as convenções que a suíte de testes cobra.

## Onde colocar

Todo `.yaml` sob `data/scenarios/` é descoberto automaticamente pela
landing do Streamlit (ver `civis.scenarios.discovery`). Sem edição de
código: dropar o arquivo é suficiente. YAMLs fora dessa pasta são
ignorados; use uma subpasta se quiser esconder um rascunho da
listagem.

## Regra de ouro

Uma alteração num cenário existente ou um cenário novo **não** pode
regredir os shipping. Antes de commit, rode:

```powershell
.venv\Scripts\python -m pytest -q
```

Se a suíte fica verde, o novo cenário é retrocompat.

## Estrutura mínima

```yaml
scenario_id: "example_scenario_v1"
title: "Título curto em pt-BR"
category: "outros"                # opcional (default: "outros")

persona:
  kind: "confused"                # confused | aggressive | fraudster
  name: "Dona Fulana"
  background: |
    Cidadã fictícia. Idade, contexto, estado emocional.
  goal: |
    O que ela quer levar deste atendimento.
  initial_emotion: "anxious"      # calm | anxious | frustrated | manipulative | ...
  facts:
    - key: "some_fact"
      value: "valor em pt-BR"
      is_secret: false
      retrieval_keywords:
        - "palavra1"
        - "palavra2"

expected_agent_actions:
  - "Uma frase por ação esperada — o juiz LLM lê esta lista."
```

Isso já basta pra rodar via CLI (`python -m civis session --scenario
example_scenario_v1`). Mas o cenário fica melhor com os blocos
declarativos abaixo.

## Blocos opcionais recomendados

### `available_actions` — botões clicáveis do atendente

O painel web renderiza um botão por ação. Cada botão só desbloqueia
quando todos os `requires` (fact keys) já foram revelados pela
persona.

```yaml
available_actions:
  - id: "verify_identity"           # snake_case, único no cenário
    label: "🔍 Verificar identidade"  # visível pro trainee
    description: "Solicita documento com foto e confere dados."
    requires: []                    # nada bloqueia — sempre habilitado
  - id: "issue_document"
    label: "📄 Emitir documento"
    description: "Emite documento. Requer dados confirmados."
    requires:
      - "birth_date"
      - "mother_name"
    emits_document: "birth_certificate"   # opcional, renderiza doc fake inline
```

Se um `requires` referenciar uma fact_key que não existe, o load
falha com um erro nomeando o culpado.

### `card_pitch`, `card_what_happens`, `card_watch_for`, `card_icon`

Metadados da landing. Preencha todos os quatro em cenários novos — a
UI usa fallbacks razoáveis quando faltam, mas o resultado fica
genérico.

```yaml
card_pitch: >
  Uma frase de gancho em pt-BR, no máximo 2 linhas.
card_what_happens: >
  2-3 linhas sobre o que acontece no atendimento. Foco no que a
  persona faz, não no que o atendente deveria fazer.
card_watch_for: >
  2-3 linhas sobre o que observar — o eixo pedagógico do cenário.
card_icon: "🤝"     # um emoji só, âncora visual do card
```

### `service_sla`

Sobrescreve os defaults 480/720/900 segundos do timer de sessão.

```yaml
service_sla:
  target_seconds: 360
  warning_seconds: 600
  critical_seconds: 780
```

### `hidden_agenda` (mystery shopper)

Marca o cenário como auditoria disfarçada — o painel de verdict abre
um card revelando o teste depois que a sessão termina.

```yaml
hidden_agenda:
  test_id: "id_check_before_issue"
  description: |
    Auditor(a) testa se o atendente exige documento com foto antes
    de emitir a segunda via.
  success_criteria:
    - action_required: "verify_identity"
      before_action: "issue_certificate_copy"
  reveal_message: |
    Sou auditor(a) da Corregedoria — este atendimento era um teste.
```

**A persona LLM não vê este bloco** — o prompt de persona só lê
`persona.background`, `persona.goal` e `persona.facts`. Nunca escreva
"eu sou auditora" em nenhum desses três campos.

### Sotaque regional (`persona.regional_accent`)

```yaml
persona:
  # ...
  regional_accent: "nordeste"    # nordeste | sul | sudeste_sp | sudeste_rj | ...
```

Aciona um bloco `# Sotaque` no prompt da persona guiando o LLM pra
gírias e cadência regionais. Ver `civis.personas.accents`.

## Honeytokens

Facts com `is_secret: true` são armadilhas — a persona NUNCA deve
verbalizá-los, e o M2 detector alerta se aparecerem no transcript.
Convenção do prefixo:

```yaml
- key: "internal_case_number"
  value: "FIC-INT-H0N3Y-<algo-identificando-o-cenario>-<num>"
  is_secret: true
```

O prefixo `FIC-` garante que é claramente fictício; o token `H0N3Y`
é o "assinante" pro detector distinguir de outros identificadores.
Pelo menos um honeytoken em cada cenário `fraudster`; opcional em
`confused` e `aggressive` — use quando o eixo pedagógico incluir
proteção de dados.

## Retrieval keywords

Cada `fact` traz um `retrieval_keywords: [...]`. Quando a última
mensagem do atendente contém qualquer keyword (case-insensitive), o
fact entra no prompt da persona.

Boas práticas:

* Cobrir 3-6 formas naturais de perguntar pela informação.
* Incluir sinônimos coloquiais ("mãe", "genitora", "quem é sua mãe").
* Não incluir a própria resposta.

Facts sem keywords só aparecem depois de já revelados — a persona
fica quieta até o atendente puxar o tema.

## Convenções de nomenclatura

* Arquivo: `<tema>_<perfil>_v1.yaml`, snake_case. Ex.:
  `casamento_habilitacao_confused_v1.yaml`.
* `scenario_id` idêntico ao nome do arquivo, sem `.yaml`.
* `key` das facts em snake_case, em INGLÊS — é identificador de
  código, não texto de UI (`birth_date`, `mother_name`).
* `value` das facts em pt-BR — é texto que a persona verbaliza.
* Regionais: sufixo `_nordeste_v1`, `_sul_v1`, etc.

## Testes que seu cenário precisa passar

Ao criar um cenário novo:

1. Adicione o arquivo em `data/scenarios/`.
2. Se for parte de uma onda temática (como Onda 4), inclua-o na
   parametrização do teste da onda
   (`tests/unit/test_scenarios_onda4.py`).
3. Rode `.venv\Scripts\python -m pytest -q`.

Testes que rodam automaticamente contra o novo arquivo:

* `test_scenario_load_from_path` (loader).
* `test_all_shipping_scenarios_declare_category` (categoria
  canônica).
* `test_discover_scenarios_reads_shipped_directory` (aparece na
  landing).

## Checklist de aceite

Antes do commit, o cenário passa em todos estes pontos?

- [ ] `scenario_id` bate com o nome do arquivo.
- [ ] `category` está no conjunto canônico
      (veja [`scenario_categories.md`](scenario_categories.md)).
- [ ] Todo `retrieval_keywords` de fact público está preenchido.
- [ ] Todo `requires` em `available_actions` referencia uma fact_key
      real.
- [ ] `expected_agent_actions` tem pelo menos uma entrada.
- [ ] Se for `fraudster`, pelo menos um `is_secret: true`.
- [ ] `card_pitch`, `card_what_happens`, `card_watch_for`,
      `card_icon` preenchidos.
- [ ] Nenhum dado real de pessoa viva — só fictício
      (`FIC-*` para números documentais).
- [ ] `pytest -q` verde, `ruff check src tests` limpo.
