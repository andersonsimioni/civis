"""
Adversarial evaluation subsystem.

Phase C artifacts live here:
    - battery.py                    Declarative OWASP LLM Top 10 battery + runner.
    - mock_providers.py             Recording/scripted providers for offline runs.
    - honeytoken_detector.py        Post-session leak detection (C.2).
    - judge_deceiver_pointwise.py   Adapted JudgeDeceiver attack for rubric judges (C.4).
    - mock_judges.py                Vulnerable vs. robust judge mocks used by C.4.
    - report.py                     Consolidated security-report generator (C.5).

All modules are read-heavy string-matching + pydantic — no ML dependencies.
Tests never touch a real LLM API; the CLI opt-in gate is env var CIVIS_RUN_REAL_LLM=1.
"""
