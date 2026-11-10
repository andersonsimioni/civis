# CIVIS — Relatório do Estudo de Concordância

Gerado por `scripts/compute_kappa.py`.

## Juiz automático vs Avaliador 1

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.517 | moderada |
| data_protection | 0.000 | leve |
| protocol_adherence | 0.122 | leve |
| communication | 0.302 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.412** (moderada) |
| linear | 0.309 |
| unweighted | 0.176 |

**IC 95% (bootstrap, quadratic):** [0.271, 0.536]

### Métricas complementares (concordância ordinal)

Kappa quadrático pune bias sistemático mesmo quando os avaliadores concordam na ordenação. As métricas abaixo isolam esses componentes: Spearman ignora shift de calibração; within-1 mede quantos pares caem no mesmo bairro ordinal; mean_diff quantifica o shift sistemático (positivo = juiz A sistematicamente maior).

| Critério | Spearman | within-1 | exact | mean_diff (A−B) |
|---|---|---|---|---|
| fact_verification | 0.711 | 77% | 33% | +1.03 |
| data_protection | — | 100% | 97% | +0.03 |
| protocol_adherence | 0.381 | 33% | 10% | +1.83 |
| communication | 0.526 | 83% | 27% | +0.77 |
| **agregado** | **0.554** | **73%** | **42%** | **+0.92** |

## Juiz automático vs Avaliador 2

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.517 | moderada |
| data_protection | 0.000 | leve |
| protocol_adherence | 0.122 | leve |
| communication | 0.302 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.412** (moderada) |
| linear | 0.309 |
| unweighted | 0.176 |

**IC 95% (bootstrap, quadratic):** [0.271, 0.536]

### Métricas complementares (concordância ordinal)

Kappa quadrático pune bias sistemático mesmo quando os avaliadores concordam na ordenação. As métricas abaixo isolam esses componentes: Spearman ignora shift de calibração; within-1 mede quantos pares caem no mesmo bairro ordinal; mean_diff quantifica o shift sistemático (positivo = juiz A sistematicamente maior).

| Critério | Spearman | within-1 | exact | mean_diff (A−B) |
|---|---|---|---|---|
| fact_verification | 0.711 | 77% | 33% | +1.03 |
| data_protection | — | 100% | 97% | +0.03 |
| protocol_adherence | 0.381 | 33% | 10% | +1.83 |
| communication | 0.526 | 83% | 27% | +0.77 |
| **agregado** | **0.554** | **73%** | **42%** | **+0.92** |

## Avaliador 1 vs Avaliador 2 (sanity)

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 1.000 | quase perfeita |
| data_protection | 1.000 | quase perfeita |
| protocol_adherence | 1.000 | quase perfeita |
| communication | 1.000 | quase perfeita |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **1.000** (quase perfeita) |
| linear | 1.000 |
| unweighted | 1.000 |

**IC 95% (bootstrap, quadratic):** [1.000, 1.000]

### Métricas complementares (concordância ordinal)

Kappa quadrático pune bias sistemático mesmo quando os avaliadores concordam na ordenação. As métricas abaixo isolam esses componentes: Spearman ignora shift de calibração; within-1 mede quantos pares caem no mesmo bairro ordinal; mean_diff quantifica o shift sistemático (positivo = juiz A sistematicamente maior).

| Critério | Spearman | within-1 | exact | mean_diff (A−B) |
|---|---|---|---|---|
| fact_verification | 1.000 | 100% | 100% | +0.00 |
| data_protection | 1.000 | 100% | 100% | +0.00 |
| protocol_adherence | 1.000 | 100% | 100% | +0.00 |
| communication | 1.000 | 100% | 100% | +0.00 |
| **agregado** | **1.000** | **100%** | **100%** | **+0.00** |
