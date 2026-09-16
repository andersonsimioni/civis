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

    0. Sair

MENU
}

while true; do
    show_menu
    read -r -p "Escolha [0-12]: " choice
    echo

    case "$choice" in
        1)  streamlit run src/civis/web/app.py ;;
        2)  python -m civis session --scenario certificate_duplicate_confused_v1 ;;
        3)  python -m civis session --scenario rg_urgent_aggressive_v1 ;;
        4)  python -m civis session --scenario certificate_thirdparty_fraudster_v1 ;;
        5)  python -m pytest -q ;;
        6)  python -m ruff check src tests ;;
        7)  python scripts/run_study_v2.py generate --n-sessions 30 ;;
        8)  python scripts/run_study_v2.py rejudge --judge-config claude_judge.toml ;;
        9)  python scripts/run_study_v2.py export-csvs ;;
        10) python scripts/run_study_v2.py analyze ;;
        11) python -m civis adversarial run --target both \
                --output reports/adversarial_run.json ;;
        12) python -m civis adversarial judge-deceiver \
                --output reports/judge_deceiver_run.json ;;
        0)  exit 0 ;;
        *)  echo "[civis] opção inválida: $choice" ;;
    esac

    echo
    read -r -p "Enter para voltar ao menu..." _
done
