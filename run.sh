#!/usr/bin/env bash
# CIVIS launcher (bash / git-bash / WSL). Same menu as run.bat.
# Usage: `./run.sh` from the repo root.

set -e
cd "$(dirname "$0")"

# Activate .venv (create it if missing). Windows git-bash puts activate under
# Scripts/, POSIX systems under bin/ — try both.
activate_venv() {
    if [ -f .venv/Scripts/activate ]; then
        # shellcheck disable=SC1091
        source .venv/Scripts/activate
    elif [ -f .venv/bin/activate ]; then
        # shellcheck disable=SC1091
        source .venv/bin/activate
    else
        echo "[civis] falha ao localizar activate script no .venv" >&2
        exit 1
    fi
}

if [ ! -d .venv ]; then
    echo "[civis] .venv não encontrado — rodando setup..."
    python -m venv .venv
    activate_venv
    pip install -e ".[dev]"
else
    activate_venv
fi

show_menu() {
    cat <<'MENU'

============================================================
  CIVIS - Cidadão Virtual Simulado
============================================================

  Demo e sessão
    1. Abrir demo Streamlit
    2. Sessão CLI - cidadã confusa
    3. Sessão CLI - cidadão agressivo
    4. Sessão CLI - fraudador

  Qualidade
    5. Rodar suite de testes
    6. Rodar ruff (lint)

  Estudo M1-A (rodar em ordem)
    7. Gerar 30 sessões (Ollama, ~2-3h)
    8. Rejudge com Claude (~R$ 30-50)
    9. Exportar CSVs
   10. Calcular kappa e gerar relatório

  Adversarial
   11. Rodar bateria OWASP (mock providers)
   12. Rodar JudgeDeceiver-pointwise (mock)

  Pitch
   13. Preencher deck com números reais (F-final)
   14. Emitir certificado do atendente

  Setup
   15. Trocar para Claude (persona + juiz)

    0. Sair

MENU
}

while true; do
    show_menu
    read -r -p "Escolha [0-15]: " choice
    echo

    # Preflight helper — call before any Ollama-dependent command. Aborts
    # the chosen action with a clear message if Ollama is down or the models
    # are not pulled.
    preflight() {
        python scripts/preflight_ollama.py --interactive
    }

    case "$choice" in
        1)  preflight && streamlit run src/civis/web/app.py ;;
        2)  preflight && python -m civis session \
                --scenario certificate_duplicate_confused_v1 ;;
        3)  preflight && python -m civis session \
                --scenario rg_urgent_aggressive_v1 ;;
        4)  preflight && python -m civis session \
                --scenario certificate_thirdparty_fraudster_v1 ;;
        5)  python -m pytest -q ;;
        6)  python -m ruff check src tests ;;
        7)  preflight && python scripts/run_study_v2.py generate --n-sessions 30 ;;
        8)  python scripts/run_study_v2.py rejudge --judge-config claude_judge.toml ;;
        9)  python scripts/run_study_v2.py export-csvs ;;
        10) python scripts/run_study_v2.py analyze ;;
        11) python -m civis adversarial run --target both \
                --output reports/adversarial_run.json ;;
        12) python -m civis adversarial judge-deceiver \
                --output reports/judge_deceiver_run.json ;;
        13) python scripts/fill_pitch_deck.py ;;
        # Onda-1 F2.4: ask for the attendant's name and delegate to
        # `civis certify`. Empty input short-circuits before invoking the
        # CLI (which would also exit 2, but we save the round-trip).
        14) read -r -p "Nome completo do atendente: " _cert_name
            if [ -n "${_cert_name// }" ]; then
                python -m civis certify --agent-name "$_cert_name"
            else
                echo "[civis] nome vazio — abortando."
            fi
            ;;
        # Option 15: install the all-Anthropic config so both persona and
        # judge run on Claude. Fixes the Qwen-drifts-to-Chinese issue.
        15)
            if [ -n "$APPDATA" ]; then
                target_dir="$APPDATA/civis"
            else
                target_dir="${XDG_CONFIG_HOME:-$HOME/.config}/civis"
            fi
            mkdir -p "$target_dir"
            cp data/configs/config.all-anthropic.example.toml "$target_dir/config.toml"
            echo "Config instalada em $target_dir/config.toml"
            if [ -z "$ANTHROPIC_API_KEY" ]; then
                echo "AVISO: ANTHROPIC_API_KEY não está setada."
                echo "  Windows: setx ANTHROPIC_API_KEY sk-ant-... (abra novo cmd)"
                echo "  Linux/Mac: export ANTHROPIC_API_KEY=sk-ant-..."
            else
                echo "OK: ANTHROPIC_API_KEY detectada."
                echo "Escolha a opção 1 para abrir o Streamlit rodando com Claude."
            fi
            ;;
        0)  exit 0 ;;
        *)  echo "[civis] opção inválida: $choice" ;;
    esac

    echo
    read -r -p "Enter para voltar ao menu..." _
done
