# CIVIS — Relatório do Estudo de Concordância

Gerado por `scripts/compute_kappa.py`.

## Juiz automático vs Avaliador 1

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.542 | moderada |
| data_protection | — | indefinido |
| protocol_adherence | 0.544 | moderada |
| communication | 0.354 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.643** (substancial) |
| linear | 0.489 |
| unweighted | 0.326 |

**IC 95% (bootstrap, quadratic):** [0.530, 0.729]

### Métricas complementares (concordância ordinal)

Kappa quadrático pune bias sistemático mesmo quando os avaliadores concordam na ordenação. As métricas abaixo isolam esses componentes: Spearman ignora shift de calibração; within-1 mede quantos pares caem no mesmo bairro ordinal; mean_diff quantifica o shift sistemático (positivo = juiz A sistematicamente maior).

| Critério | Spearman | within-1 | exact | mean_diff (A−B) |
|---|---|---|---|---|
| fact_verification | 0.764 | 77% | 23% | +0.97 |
| data_protection | — | 100% | 100% | +0.00 |
| protocol_adherence | 0.498 | 97% | 50% | -0.27 |
| communication | 0.620 | 87% | 33% | +0.80 |
| **agregado** | **0.686** | **90%** | **52%** | **+0.38** |

## Juiz automático vs Avaliador 2

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.542 | moderada |
| data_protection | — | indefinido |
| protocol_adherence | 0.544 | moderada |
| communication | 0.354 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.643** (substancial) |
| linear | 0.489 |
| unweighted | 0.326 |

**IC 95% (bootstrap, quadratic):** [0.530, 0.729]

### Métricas complementares (concordância ordinal)

Kappa quadrático pune bias sistemático mesmo quando os avaliadores concordam na ordenação. As métricas abaixo isolam esses componentes: Spearman ignora shift de calibração; within-1 mede quantos pares caem no mesmo bairro ordinal; mean_diff quantifica o shift sistemático (positivo = juiz A sistematicamente maior).

| Critério | Spearman | within-1 | exact | mean_diff (A−B) |
|---|---|---|---|---|
| fact_verification | 0.764 | 77% | 23% | +0.97 |
| data_protection | — | 100% | 100% | +0.00 |
| protocol_adherence | 0.498 | 97% | 50% | -0.27 |
| communication | 0.620 | 87% | 33% | +0.80 |
| **agregado** | **0.686** | **90%** | **52%** | **+0.38** |

## Avaliador 1 vs Avaliador 2 (sanity)

**N de linhas comparadas:** 120

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 1.000 | quase perfeita |
| data_protection | — | indefinido |
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
| data_protection | — | 100% | 100% | +0.00 |
| protocol_adherence | 1.000 | 100% | 100% | +0.00 |
| communication | 1.000 | 100% | 100% | +0.00 |
| **agregado** | **1.000** | **100%** | **100%** | **+0.00** |
