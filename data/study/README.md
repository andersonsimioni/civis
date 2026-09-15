# CIVIS — Pasta do Estudo de Concordância

Estrutura desta pasta:

```
data/study/
├── README.md                    (você está aqui)
├── rubric_evaluator.md          rubrica leiga, escala 0-5, 4 critérios
├── evaluator_template.csv       template CSV que cada avaliador copia
├── evaluator_1_v1.csv           (produzido durante a coleta — não versionado)
├── evaluator_2_v1.csv           (produzido durante a coleta — não versionado)
└── judge_output_v1.csv          (produzido durante a coleta — não versionado)
```

Ver `docs/study_protocol.md` para o protocolo formal (§1 a §13), incluindo procedimento, cronograma e regras de independência.

## Fluxo prático

1. Coordenador (Anderson) roda 30 sessões via CIVIS ao longo de outubro-novembro/2026, salva transcrições em `data/sessions/`.
2. Coordenador exporta escores do juiz automático para `judge_output_v1.csv` (mesmo formato do template).
3. Cada avaliador recebe uma cópia do `evaluator_template.csv` com `session_id` e `criterion` pré-preenchidos.
4. Cada avaliador salva sua planilha preenchida como `evaluator_1_v1.csv` ou `evaluator_2_v1.csv`.
5. Coordenador roda:
   ```
   python scripts/compute_kappa.py \
       --judge data/study/judge_output_v1.csv \
       --evaluator-1 data/study/evaluator_1_v1.csv \
       --evaluator-2 data/study/evaluator_2_v1.csv \
       --report reports/study_v1.md
   ```
6. Relatório final em `reports/study_v1.md`.

## Convenção de arquivos

- Arquivos `evaluator_*_v1.csv` e `judge_output_v1.csv` **não são versionados** (contêm dados de coleta em andamento). Adicionar a `.gitignore` antes da coleta iniciar.
- O template versionado é apenas `evaluator_template.csv`, com linhas de exemplo em branco para ilustrar formato.
- Nomes `_v1` são propositais — se houver iteração de rubrica no checkpoint intermediário (§11 do protocolo), a segunda rodada vira `_v2`.
