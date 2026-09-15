# CIVIS — Virtual Citizen Simulator

CIVIS is a training simulator for public-service counter agents. A
scripted persona (running on an LLM) plays a citizen with a specific
goal; a human agent plays the counter clerk; a second LLM (the "judge")
scores the interaction against a declarative rubric with cited turns.

Requirements: Python 3.12+, plus a local Ollama install for the default
persona provider.

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/Mac: source .venv/bin/activate
pip install -e .[dev]

# Pull the two default models (Ollama running on http://localhost:11434):
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull llama3.1:8b-instruct-q4_K_M

# Run a session with the shipping "confused elderly citizen" scenario:
python -m civis session --scenario certificate_duplicate_confused_v1
```

The CLI reads agent turns from stdin one line at a time and prints the
persona reply after each. Empty line or Ctrl+D closes the session. On
close, unless `--no-judge`, the judge scores the transcript against
`data/rubrics/counter_v1.yaml` and writes:

```
data/sessions/<session_id>/
    transcript.json         Ordered turn log.
    metadata.json           Scenario id + SHA-256 + provider names.
    contradictions.json     M3 rate + concrete contradiction events.
    verdict.json            Judge's 4-criteria verdict with cited turns.
    citation_issues.json    Only if the judge cited fabricated quotes.
```

## Scenarios

Shipping scenarios cover the three persona profiles required by goal O2:

| Scenario id                              | Profile     | Situation                                                    |
| ---------------------------------------- | ----------- | ------------------------------------------------------------ |
| `certificate_duplicate_confused_v1`      | Confused    | Elderly citizen wants a duplicate birth certificate.         |
| `rg_urgent_aggressive_v1`                | Aggressive  | Impatient citizen demands duplicate RG before a flight.      |
| `certificate_thirdparty_fraudster_v1`    | Fraudster   | Attempts to obtain a third party's certificate via urgency.  |

Run any of them by passing the id to `--scenario`.

## Judge configurations

The CLI enforces goal O3 (persona and judge must run on distinct catalog
entries — no self-evaluation). Two setups are supported out of the box:

**Default: Ollama-dual (no config needed).**
When no `config.toml` exists, the CLI uses `qwen2.5:7b` as persona and
`llama3.1:8b` as judge, both on `localhost:11434`. Both are open-weight
models and can run on a workstation with 16 GB of RAM. This is the
recommended dev setup — fast iteration, no API cost.

**Optional: Ollama persona + Claude judge.**
Copy `data/configs/config.claude-judge.example.toml` to your user config
path (`%APPDATA%\civis\config.toml` on Windows,
`$XDG_CONFIG_HOME/civis/config.toml` on Linux/Mac) and export
`ANTHROPIC_API_KEY`. This crosses provider families, giving the judge
architectural independence from the persona's inference stack. Use it
when you need stronger rubric reasoning than a local 8B model can
provide — for example, when running the Phase E study sessions that
feed the kappa report.

You never need to touch code to switch: `roles.persona` and
`roles.judge` point at catalog entries by key, and the factory dispatches
to the right provider (Ollama, OpenAI-compatible, or Anthropic).

## Rubric

`data/rubrics/counter_v1.yaml` describes each score level (0–5) per
criterion. The same descriptions appear in
`data/study/rubric_evaluator.md`, so the LLM judge and the human
evaluators in the Phase E kappa study score against the SAME yardstick.

## Development

```bash
python -m pytest -q
python -m ruff check src tests
```

The CI workflow at `.github/workflows/ci.yml` runs both on every push.
