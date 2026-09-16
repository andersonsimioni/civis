@echo off
REM CIVIS launcher (Windows). Runs the most common tasks from a single menu.
REM Usage: double-click, or `run.bat` from a Command Prompt at the repo root.
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [civis] .venv nao encontrado — rodando setup...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -e ".[dev]"
) else (
    call .venv\Scripts\activate.bat
)

:menu
echo.
echo ============================================================
echo   CIVIS - Cidadao Virtual Simulado
echo ============================================================
echo.
echo   Demo e sessao
echo     1. Abrir demo Streamlit
echo     2. Sessao CLI - cidada confusa
echo     3. Sessao CLI - cidadao agressivo
echo     4. Sessao CLI - fraudador
echo.
echo   Qualidade
echo     5. Rodar suite de testes
echo     6. Rodar ruff (lint)
echo.
echo   Estudo M1-A (rodar em ordem)
echo     7. Gerar 30 sessoes (Ollama, ~2-3h)
echo     8. Rejudge com Claude (~R$ 30-50)
echo     9. Exportar CSVs
echo    10. Calcular kappa e gerar relatorio
echo.
echo   Adversarial
echo    11. Rodar bateria OWASP (mock providers)
echo    12. Rodar JudgeDeceiver-pointwise (mock)
echo.
echo   Pitch
echo    13. Preencher deck com numeros reais (F-final)
echo    14. Emitir certificado do atendente
echo.
echo    0. Sair
echo.

set /p choice="Escolha [0-14]: "
echo.

REM Options that hit Ollama (1-4 and 7) run a preflight first — it verifies
REM the server is up AND the required models are pulled, offering to pull
REM them if missing. Exit != 0 short-circuits the actual command.
if "%choice%"=="1"  python scripts\preflight_ollama.py --interactive && streamlit run src\civis\web\app.py
if "%choice%"=="2"  python scripts\preflight_ollama.py --interactive && python -m civis session --scenario certificate_duplicate_confused_v1
if "%choice%"=="3"  python scripts\preflight_ollama.py --interactive && python -m civis session --scenario rg_urgent_aggressive_v1
if "%choice%"=="4"  python scripts\preflight_ollama.py --interactive && python -m civis session --scenario certificate_thirdparty_fraudster_v1
if "%choice%"=="5"  python -m pytest -q
if "%choice%"=="6"  python -m ruff check src tests
if "%choice%"=="7"  python scripts\preflight_ollama.py --interactive && python scripts\run_study_v2.py generate --n-sessions 30
if "%choice%"=="8"  python scripts\run_study_v2.py rejudge --judge-config claude_judge.toml
if "%choice%"=="9"  python scripts\run_study_v2.py export-csvs
if "%choice%"=="10" python scripts\run_study_v2.py analyze
if "%choice%"=="11" python -m civis adversarial run --target both --output reports\adversarial_run.json
if "%choice%"=="12" python -m civis adversarial judge-deceiver --output reports\judge_deceiver_run.json
if "%choice%"=="13" python scripts\fill_pitch_deck.py
REM Onda-1 F2.4: prompt for the attendant's name, then call `civis certify`.
REM setlocal enabledelayedexpansion (top of file) makes !var! work inside
REM the block below — %var% would expand at parse time and be empty.
if "%choice%"=="14" (
    set _cert_name=
    set /p _cert_name="Nome completo do atendente: "
    if defined _cert_name (
        python -m civis certify --agent-name "!_cert_name!"
    ) else (
        echo [civis] nome vazio — abortando.
    )
)
if "%choice%"=="0"  goto end

echo.
pause
goto menu

:end
endlocal
