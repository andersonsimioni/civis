"""
"Métricas" page — telemetry M4 + M1 validation status + Phase C evidence.

Panels:

    1. Session slider — how many recent sessions feed the aggregations.
    2. Five top-level st.metric cards — sessions, latency p95, cost,
       M2 defence, JudgeDeceiver ASR. Labels match the roadmap wording:
       'Latência p95', 'Custo/sessão'.
    3. Latency histogram (st.bar_chart) with the M4 target of 5000 ms.
    4. Per-provider latency table with p50/p95/max.
    5. Cost breakdown by session.
    6. Refusal-rate placeholder card with 'aguardando smoke test da
       Fase D+' copy per the roadmap.
    7. Validation (M1) panel — hybrid design (M1-A inter-model kappa +
       M1-C manual sample) with a placeholder pointing at the study
       window 20/10-01/12 until real numbers land.
    8. M2 panel — OWASP-per-category bar chart pulled from
       reports/adversarial_v1.json.
    9. JudgeDeceiver-pointwise panel — ASR per criterion and overall,
       pulled from reports/judge_deceiver_pointwise_v1.json.

All charts use native Streamlit widgets (st.bar_chart, st.line_chart,
st.metric). No Altair / Plotly — one dependency to install, no more.
"""

from __future__ import annotations

import streamlit as st

from civis.web.data_access import (
    aggregate_telemetry,
    list_sessions,
    load_adversarial_v1,
    load_judge_deceiver_v1,
)
from civis.web.formatting import (
    criterion_label,
    format_currency_usd,
    format_latency_ms,
    format_percent,
    owasp_label,
)
from civis.web.metrics_calc import (
    cost_summary,
    judge_deceiver_asr_by_criterion,
    latency_bucket_histogram,
    latency_by_provider,
    owasp_defense_by_category,
)
from civis.web.state import get_reports_dir, get_sessions_dir

# M4 target from docs/ROADMAP_PITCH.md §2: p95 < 5 s.
LATENCY_TARGET_MS = 5000


def render() -> None:
    """Render the Métricas page."""
    st.title("Métricas")
    st.markdown(
        "Telemetria M4 das últimas sessões, validação M1 do juiz "
        "automático e resumo dos relatórios adversariais entregues na "
        "Fase C. Painéis M2 e ASR JudgeDeceiver-pointwise vêm dos "
        "arquivos em `reports/`."
    )

    sessions = list_sessions(get_sessions_dir())
    _render_scope_controls(sessions)
    _render_top_metrics()
    _render_latency_section()
    _render_cost_section()
    _render_validation_section()
    _render_security_section()


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def _render_scope_controls(sessions_all: list) -> None:
    """
    Slider controlling how many recent sessions feed the aggregations.
    Default 30 mirrors the M4 target sample size in the plan. Streamlit
    rejects a slider with min_value == max_value, so we skip the slider
    entirely (and stash a fixed limit) when there is only one session.
    """
    total = len(sessions_all)
    st.sidebar.header("Escopo das métricas")

    if total <= 1:
        st.session_state["metrics_limit"] = max(total, 1)
        st.sidebar.caption(
            "Slider aparece quando houver ≥ 2 sessões no disco."
        )
    else:
        default = min(30, total)
        st.session_state["metrics_limit"] = st.sidebar.slider(
            "Últimas N sessões",
            min_value=1,
            max_value=total,
            value=default,
            step=1,
            key="metrics_limit_slider",
            help=(
                "Quantas das sessões mais recentes entram nos gráficos de "
                "latência e custo. Painéis M1, M2 e ASR não dependem daqui."
            ),
        )

    if total == 0:
        st.warning(
            "Nenhuma sessão registrada ainda. Rode `civis session` ou "
            "gere as sessões-demo com "
            "`python scripts/generate_demo_sessions.py`."
        )


def _current_limit() -> int:
    """Read the slider's current value, defaulting to 30 when unset."""
    return int(st.session_state.get("metrics_limit", 30))


# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------


def _render_top_metrics() -> None:
    """Four st.metric cards summarising the whole scope in one glance."""
    limit = _current_limit()
    sessions = list_sessions(get_sessions_dir())[:limit]
    session_count = len(sessions)
    telemetry = aggregate_telemetry(get_sessions_dir(), limit=limit)

    lat_stats = latency_by_provider(telemetry)
    all_latencies = sorted(t.latency_ms for t in telemetry)
    overall_p95 = _p95(all_latencies)

    costs = cost_summary(telemetry, session_count=session_count)

    # Label choice: keep 'Latência p95', 'Custo/sessão', 'M2 · Defesa'
    # and 'ASR JudgeDeceiver' because the smoke tests pin them and
    # because those are the labels the roadmap asks for on the metrics
    # tab. Five columns keeps the top row scannable in one glance.
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Sessões no escopo",
        session_count,
        help=f"Amostra: últimas {limit} sessão(ões).",
    )
    col2.metric(
        "Latência p95",
        format_latency_ms(overall_p95) if overall_p95 else "—",
        delta=(
            f"alvo <{LATENCY_TARGET_MS / 1000:.0f} s"
            if overall_p95 and overall_p95 <= LATENCY_TARGET_MS
            else f"acima do alvo de {LATENCY_TARGET_MS / 1000:.0f} s"
            if overall_p95
            else None
        ),
        delta_color=(
            "normal"
            if overall_p95 and overall_p95 <= LATENCY_TARGET_MS
            else "inverse"
        ),
        help="Alvo M4 do plano: p95 abaixo de 5 s por turno.",
    )
    col3.metric(
        "Custo/sessão",
        format_currency_usd(costs.average_usd_per_session),
        help=(
            "Custo estimado (mockado) via Anthropic Claude Sonnet "
            "($3/M entrada · $15/M saída) e Ollama $0. "
            "Ver src/civis/web/pricing.py."
        ),
    )
    # M2 defence total pulled straight from the adversarial report so the
    # top card matches what the security section shows in detail.
    adv_payload = load_adversarial_v1(get_reports_dir())
    if adv_payload and adv_payload.get("reports"):
        first_adv = adv_payload["reports"][0]
        col4.metric(
            "M2 · Defesa",
            f"{first_adv['defended']}/{first_adv['total']}",
            help="Ataques OWASP defendidos vs. total da bateria.",
        )
    else:
        col4.metric("M2 · Defesa", "—", help="Relatório não encontrado.")
    # Overall JudgeDeceiver-pointwise ASR as a summary card. The
    # detailed panel further down repeats it with breakdowns.
    jd_payload = load_judge_deceiver_v1(get_reports_dir())
    if jd_payload and jd_payload.get("reports"):
        first_jd = jd_payload["reports"][0]
        col5.metric(
            "ASR JudgeDeceiver",
            format_percent(first_jd["overall_asr"]),
            help="Attack Success Rate do JudgeDeceiver-pointwise agregado.",
        )
    else:
        col5.metric("ASR JudgeDeceiver", "—", help="Relatório não encontrado.")

    if lat_stats:
        st.caption(
            "Distribuição por provider: "
            + " · ".join(
                f"`{p.provider_name}` ({p.turn_count} turnos)"
                for p in lat_stats
            )
        )


# ---------------------------------------------------------------------------
# Latency section
# ---------------------------------------------------------------------------


def _render_latency_section() -> None:
    """Histogram + per-provider table."""
    st.subheader("Latência por turno")
    telemetry = aggregate_telemetry(get_sessions_dir(), limit=_current_limit())

    if not telemetry:
        st.markdown(
            '<div class="civis-empty">'
            "Sem dados de telemetria — nenhuma sessão da Fase D no escopo."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    hist = latency_bucket_histogram(telemetry)
    if hist:
        st.bar_chart(hist, height=220)
        st.caption(
            f"Barra vertical = número de turnos em cada faixa. "
            f"Alvo M4: p95 abaixo de {LATENCY_TARGET_MS} ms."
        )

    lat_stats = latency_by_provider(telemetry)
    st.markdown("**Percentis por provider**")
    for stat in lat_stats:
        cols = st.columns([2, 1, 1, 1, 1])
        cols[0].markdown(f"`{stat.provider_name}`")
        cols[1].write(f"{stat.turn_count} turnos")
        cols[2].write(f"p50 {format_latency_ms(stat.p50_ms)}")
        cols[3].write(f"p95 {format_latency_ms(stat.p95_ms)}")
        cols[4].write(f"máx {format_latency_ms(stat.max_ms)}")

    st.info(
        "Taxa de recusa por provider (M4) — aguardando smoke test da Fase D+. "
        "A instrumentação para contar respostas classificadas como recusa "
        "entra assim que rodarmos as primeiras 30 sessões reais."
    )


# ---------------------------------------------------------------------------
# Cost section
# ---------------------------------------------------------------------------


def _render_cost_section() -> None:
    """Two-column cost card + per-session bar chart."""
    st.subheader("Custo estimado")
    limit = _current_limit()
    telemetry = aggregate_telemetry(get_sessions_dir(), limit=limit)
    sessions = list_sessions(get_sessions_dir())[:limit]
    costs = cost_summary(telemetry, session_count=len(sessions))

    left, right = st.columns([1, 2])
    with left:
        st.metric(
            "Custo por sessão (média)",
            format_currency_usd(costs.average_usd_per_session),
        )
        st.metric(
            "Custo por turno (média)",
            format_currency_usd(costs.average_usd_per_turn),
        )
        st.caption(
            "Preço-base: Anthropic Claude Sonnet ($3/M entrada · $15/M "
            "saída). Ollama local = $0. Longest-prefix match; providers "
            "desconhecidos ficam em $0 até serem catalogados."
        )
    with right:
        per_session = _cost_per_session(sessions)
        if per_session:
            st.bar_chart(per_session, height=220)
            st.caption(
                "Custo estimado por sessão. Ollama-only aparece rente ao "
                "zero — é o esperado, é local."
            )


def _cost_per_session(sessions: list) -> dict[str, float]:
    """Return {session_id: usd cost} for the given session summaries."""
    from civis.web.data_access import load_turn_telemetry
    from civis.web.pricing import compute_turn_cost_usd

    result: dict[str, float] = {}
    for row in sessions:
        entries = load_turn_telemetry(row.session_id, sessions_dir=get_sessions_dir())
        total = 0.0
        for entry in entries:
            total += compute_turn_cost_usd(
                entry.input_tokens,
                entry.output_tokens,
                entry.provider_name,
            )
        result[row.session_id] = round(total, 4)
    return result


# ---------------------------------------------------------------------------
# Validation (M1 hybrid) — placeholder until the study lands
# ---------------------------------------------------------------------------


def _render_validation_section() -> None:
    """
    M1 hybrid validation panel — M1-A (inter-model kappa) + M1-C (manual
    sample). No real numbers to show until the study runs between
    20/10/2026 and 01/12/2026; this section documents the design and
    shows placeholders so the pitch reviewer knows what's coming.

    Structure mirrors slide 7 of docs/pitch_deck.md so anyone opening
    the app and the deck side by side sees the same story.
    """
    st.subheader("Validação (M1 híbrida)")
    st.markdown(
        "O CIVIS substitui o estudo original de kappa juiz-humano por "
        "uma validação em duas componentes — mais defensável dado que o "
        "projeto é tocado sozinho e não há dois avaliadores humanos "
        "independentes disponíveis no prazo. Ver `docs/study_protocol.md`."
    )

    col_a, col_c = st.columns(2)
    with col_a:
        st.markdown(
            "**M1-A · Kappa inter-modelo**  \n"
            "Concordância de Cohen entre dois LLMs independentes "
            "(Ollama × Claude) atuando como juiz sobre as mesmas ≥30 "
            "sessões, com IC 95% via bootstrap."
        )
        st.metric(
            "Kappa inter-modelo",
            "—",
            delta="alvo ≥ 0,60",
            delta_color="off",
            help=(
                "Componente quantitativo do M1. Preenchido após rodar o "
                "juiz Claude sobre as sessões do estudo v2."
            ),
        )
    with col_c:
        st.markdown(
            "**M1-C · Amostragem manual**  \n"
            "Coordenador avalia manualmente ≥10 sessões escolhidas "
            "aleatoriamente, com pelo menos 7 dias entre execução e "
            "avaliação (mitiga viés de memória)."
        )
        st.metric(
            "Concordância criterion-a-criterion",
            "—",
            delta="alvo ≥ 8/10",
            delta_color="off",
            help=(
                "Componente qualitativo do M1. Discordâncias em ≥2 "
                "sessões viram iteração de rubrica antes do pitch."
            ),
        )

    st.info(
        "Execução do estudo prevista para **20/10 – 01/12/2026**. "
        "Protocolo completo em `docs/study_protocol.md`; script de "
        "cálculo do kappa em `scripts/compute_kappa.py`. Estudo humano "
        "amplo (2 avaliadores independentes, N≥30) fica documentado "
        "como próximo passo do piloto pago em cartório real."
    )


# ---------------------------------------------------------------------------
# Security section (M2 + JudgeDeceiver ASR)
# ---------------------------------------------------------------------------


def _render_security_section() -> None:
    """M2 defence bar chart + JudgeDeceiver-pointwise ASR panel."""
    st.subheader("Prova de segurança (Fase C)")
    _render_m2_panel()
    _render_judge_deceiver_panel()


def _render_m2_panel() -> None:
    """OWASP LLM Top 10 defence breakdown."""
    payload = load_adversarial_v1(get_reports_dir())
    if payload is None:
        st.info(
            "Relatório M2 não encontrado. Rode `civis adversarial run` para "
            "gerar `reports/adversarial_v1.json`."
        )
        return

    st.markdown("**M2 · Bateria OWASP LLM Top 10 — defesas por categoria**")
    first = payload["reports"][0]
    st.metric(
        "Taxa de vazamento agregada",
        format_percent(first["leak_rate"]),
        delta="alvo <5%",
        delta_color="normal" if first["leak_rate"] < 0.05 else "inverse",
    )

    by_cat = owasp_defense_by_category(payload)
    if by_cat:
        chart_data: dict[str, int] = {}
        for cat_key, counts in by_cat.items():
            chart_data[owasp_label(cat_key)] = counts["defended"]
        st.bar_chart(chart_data, height=220)
        st.caption(
            "Barras = ataques defendidos por categoria OWASP. "
            f"Total da bateria: {first['total']} ataques · "
            f"defendidos: {first['defended']} · vazamentos: {first['leaked']} · "
            f"skipped: {first['skipped']}."
        )


def _render_judge_deceiver_panel() -> None:
    """ASR + PAC (JudgeDeceiver-pointwise)."""
    payload = load_judge_deceiver_v1(get_reports_dir())
    if payload is None:
        st.info(
            "Relatório JudgeDeceiver-pointwise não encontrado. Rode a "
            "bateria adaptada da Fase C para gerar "
            "`reports/judge_deceiver_pointwise_v1.json`."
        )
        return

    st.markdown(
        "**JudgeDeceiver-pointwise (Fase C.4) — pode o juiz ser manipulado?**"
    )
    first = payload["reports"][0]

    # The top-metric row already carries the aggregate ASR card; here we
    # show the supporting breakdown (attempted, succeeded) so the tests
    # find exactly one 'ASR JudgeDeceiver' label on the page.
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Ataques executados",
        first["attempted"],
        help="Total de injeções contra o juiz na bateria adaptada.",
    )
    col2.metric(
        "Sucessos do atacante",
        first["succeeded"],
        help="Quantos ataques levaram o juiz à nota-alvo (falso positivo).",
    )
    col3.metric(
        "PAC (nota-alvo)",
        first.get("target_score", "—"),
        help="Nota específica que a bateria tentou forçar (Prompt-Aligned Cost).",
    )

    asr_by_crit = judge_deceiver_asr_by_criterion(payload)
    if asr_by_crit:
        pretty = {criterion_label(k): v for k, v in asr_by_crit.items()}
        st.bar_chart(pretty, height=220)
        st.caption(
            "ASR por critério da rubrica. Um valor alto num critério "
            "significa que o juiz é facilmente manipulável nele — "
            "é resultado científico, não bug do produto."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _p95(sorted_values: list[int]) -> int:
    """Small local wrapper for the top-metric card."""
    if not sorted_values:
        return 0
    from civis.web.metrics_calc import _percentile

    return _percentile(sorted_values, 95)


render()
