# Categorias de cenários

Toda YAML sob `data/scenarios/` carrega um campo opcional `category`
que informa em qual escopo do cartório o cenário se encaixa. O
conjunto é fechado — um valor fora da lista dispara `ValueError` no
carregamento — e serve pra três coisas:

1. Filtrar a lista de cenários na landing do Streamlit (**Nova sessão**
   → dropdown "Categoria").
2. Agrupar sessões passadas por assunto quando o volume de treinos
   crescer.
3. Balancear a suíte pedagogicamente (não deixar tudo virar cenário
   de nascimento).

## Conjunto canônico

O código-fonte da lista fica em
[`src/civis/scenarios/categories.py`](../src/civis/scenarios/categories.py).
A ordem abaixo é a ordem em que as categorias aparecem no dropdown.

| Chave YAML                    | Emoji | Label pt-BR                    | O que cobre                                                                                                     |
|-------------------------------|-------|--------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `nascimento`                  | 👶    | Nascimento                     | Assento de nascimento, segunda via de certidão, alteração de dados do nascimento.                               |
| `casamento`                   | 🤝    | Casamento                      | Habilitação, celebração, escritura, segunda via de certidão de casamento.                                       |
| `obito`                       | ⚰️    | Óbito                          | Registro de óbito, segunda via, casos que exigem IML/SVO antes do assento.                                      |
| `divorcio`                    | ✂️    | Divórcio                       | Divórcio extrajudicial (Lei 11.441/2007), consensual sem menores.                                               |
| `reconhecimento_paternidade`  | 🧬    | Reconhecimento de paternidade  | Rota administrativa (Prov. CNJ 63/2017) x rota judicial (post-mortem, litigioso).                               |
| `alteracao_nome`              | ✍️    | Alteração de nome              | Prenome, retificação por erro material, alteração de gênero (Prov. CNJ 73/2018).                                |
| `uniao_estavel`               | 💞    | União estável                  | Escritura declaratória, dissolução, regime de bens da união.                                                    |
| `averbacao`                   | 📎    | Averbação                      | Averbações de todo tipo (casamento no exterior, divórcio, sentença estrangeira, adoção).                        |
| `retificacao`                 | 🩹    | Retificação                    | Erro material fora do prenome — grafia, filiação, data de nascimento com apresentação de prova.                 |
| `emancipacao`                 | 🕊️    | Emancipação                    | Emancipação voluntária, judicial ou por casamento.                                                              |
| `outros`                      | 📂    | Outros                         | Fallback quando o cenário não cabe em nenhuma categoria acima — ou quando o eixo pedagógico é outro (procuração, autenticidade documental). |

## Retrocompatibilidade

Cenários que não declaram `category` caem automaticamente em `outros`
— nada quebra ao carregar YAMLs antigos. Todos os cenários shipping
já foram migrados; ao criar um novo, prefira declarar explicitamente.

## Quando criar uma categoria nova

Editar `CANONICAL_CATEGORIES` em `src/civis/scenarios/categories.py`,
adicionar label pt-BR em `CATEGORY_LABELS` e um emoji em
`CATEGORY_ICONS`. Rodar os testes:

```powershell
.venv\Scripts\python -m pytest tests/unit/test_session_scenario.py -q
```

O parametrizado `test_scenario_accepts_every_canonical_category` já
cobre o novo valor automaticamente.
