# CIVIS — Relatório do Estudo de Concordância

Gerado por `scripts/compute_kappa.py`.

## Juiz automático vs Avaliador 1

**N de linhas comparadas:** 40

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.554 | moderada |
| data_protection | — | indefinido |
| protocol_adherence | 0.355 | razoável |
| communication | 0.368 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.564** (moderada) |
| linear | 0.446 |
| unweighted | 0.338 |

**IC 95% (bootstrap, quadratic):** [0.332, 0.738]

## Juiz automático vs Avaliador 2

**N de linhas comparadas:** 40

### Kappa por critério (quadratic weighted)

| Critério | Kappa | Interpretação |
|---|---|---|
| fact_verification | 0.554 | moderada |
| data_protection | — | indefinido |
| protocol_adherence | 0.355 | razoável |
| communication | 0.368 | razoável |

### Agregado (todas as sessões, todos os critérios)

| Ponderação | Kappa |
|---|---|
| **quadratic (primária)** | **0.564** (moderada) |
| linear | 0.446 |
| unweighted | 0.338 |

**IC 95% (bootstrap, quadratic):** [0.332, 0.738]

## Avaliador 1 vs Avaliador 2 (sanity)

**N de linhas comparadas:** 40

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
