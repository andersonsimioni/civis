"""
Real-time coach for a live CIVIS training session (ONDA 3, C3.1).

A :class:`Coach` observes the transcript-in-progress and, on demand,
asks an LLM to suggest ONE short next-move the attendant should
consider. The suggestion sits above the chat input while the trainee
types; if the model has nothing useful to say, the coach returns
``None`` and the UI stays clean.

Design notes:
    - The coach reuses the ``LLMProvider`` interface — no new
      contract, no new dependency. In practice the web layer will
      wire the judge provider (Ollama by default) into the coach so
      the whole demo runs on a single local model.
    - We keep the prompt small and pt-BR-only. The training scenarios
      are pt-BR; asking for English hints in the middle of a pt-BR
      training would be jarring.
    - The reply-parsing rule is intentionally tolerant: an empty
      string, whitespace, or a stock refusal are all mapped to
      ``None``. A working suggestion is one non-empty pt-BR sentence.
    - Suggestion type (hint / warning / info) is inferred from the
      leading emoji the model uses. We hard-map three prefixes:
      ⚠️ / 💡 / ℹ️. Anything else defaults to ``hint``. The web layer
      colours the block accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from civis.llm.provider import LLMMessage, LLMProvider
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript

# Coach suggestions carry a compact type flag so the UI can pick a
# colour without re-parsing the message.
CoachSuggestionType = Literal["hint", "warning", "info"]


@dataclass(frozen=True)
class CoachSuggestion:
    """
    One coach suggestion delivered to the UI.

    Attributes:
        type: ``hint`` (default), ``warning`` (needs attention now),
            ``info`` (extra context, non-actionable).
        message: pt-BR sentence, roughly 15 words or less. The web
            layer prepends the emoji when rendering.
        emoji: The emoji the coach chose for its message. Used by the
            UI as an inline label; empty when the coach did not pick
            one explicitly.
    """

    type: CoachSuggestionType
    message: str
    emoji: str = ""


# Prompt template. Kept in this module so it is version-controlled
# with the parser — a change to the reply format also lives here.
_SYSTEM_PROMPT_TEMPLATE = """\
Você é um supervisor experiente observando um atendente novato em treinamento.
Analise o histórico da conversa e o objetivo do cenário. Se identificar um
próximo movimento útil que o atendente deveria fazer, forneça UMA sugestão
curta (máximo 15 palavras) em pt-BR. Se o atendente já está indo bem, responda
apenas com a palavra "OK" (sem aspas).

Formato da sugestão: comece com um dos emojis abaixo indicando urgência:
- ⚠️  Ação urgente (o atendente está prestes a errar).
- 💡  Dica (movimento que ajudaria mas não é urgente).
- ℹ️  Contexto (apenas informação útil).

Cenário: {scenario_title}
Ações esperadas do atendente: {expected_agent_actions}
Ações já executadas: {actions_done}
Fatos já revelados pelo cidadão: {revealed_facts}
"""

# The three emoji prefixes we treat as first-class. Everything else
# falls back to 'hint'.
_EMOJI_TO_TYPE: dict[str, CoachSuggestionType] = {
    "⚠️": "warning",
    "⚠": "warning",
    "💡": "hint",
    "ℹ️": "info",
    "ℹ": "info",
}


class Coach:
    """
    Observes a live session and turns it into short pt-BR hints.

    A :class:`Coach` is stateless with respect to LLM history — every
    call to :meth:`suggest_next_move` starts a fresh conversation
    with the provider. That keeps token cost per hint predictable and
    lets the web layer decide when to invoke the coach (typically
    after each persona reply).
    """

    def __init__(self, provider: LLMProvider, scenario: ScenarioFile) -> None:
        """
        Args:
            provider: The LLM used to generate suggestions. Any
                :class:`LLMProvider` works; the web layer wires the
                judge provider by default.
            scenario: The scenario the trainee is running. Its title
                and expected-action list feed the prompt.
        """
        self._provider = provider
        self._scenario = scenario

    def suggest_next_move(
        self,
        transcript: SessionTranscript,
    ) -> CoachSuggestion | None:
        """
        Ask the model for one next-move suggestion.

        Returns ``None`` when the model has nothing useful to say —
        either because it emitted an 'OK' reply or because the parsed
        content is empty. The web layer treats ``None`` as 'no hint
        this turn' and does not render the coach bubble.
        """
        messages = self._build_prompt(transcript)
        response = self._provider.complete(messages)
        return _parse_reply(response.content)

    def _build_prompt(
        self,
        transcript: SessionTranscript,
    ) -> list[LLMMessage]:
        """
        Assemble the message list for one coach call.

        The system message injects the scenario context; the user
        message dumps the current transcript so far. We keep the
        transcript short — only the last few speech turns matter for
        a suggestion — but we do not drop action or queue turns,
        because 'attendant already clicked X' is useful signal.
        """
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            scenario_title=self._scenario.title,
            expected_agent_actions=_bullet_list(self._scenario.expected_agent_actions),
            actions_done=_bullet_list(_recent_actions(transcript)),
            revealed_facts=_bullet_list(_recent_persona_snippets(transcript)),
        )
        user_prompt = _format_transcript(transcript)
        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]


# ---------------------------------------------------------------------------
# Helpers — pure functions, easy to unit test alongside the class
# ---------------------------------------------------------------------------


def _parse_reply(raw: str) -> CoachSuggestion | None:
    """
    Turn the LLM's raw text into a :class:`CoachSuggestion` or
    ``None`` when the reply signals 'no hint needed'.

    Contract mirrors the prompt: an 'OK' answer (case-insensitive,
    optionally punctuation) means the attendant is doing fine.
    """
    text = (raw or "").strip()
    if not text:
        return None
    # Cheap 'OK' detection — the model sometimes wraps the reply in
    # quotes or trailing punctuation. Strip common wrapping.
    stripped = text.strip('".!\'').strip()
    if stripped.lower() in {"ok", "okay", "ok.", "tudo certo"}:
        return None

    emoji, message = _split_emoji_prefix(text)
    if not message:
        return None
    return CoachSuggestion(
        type=_EMOJI_TO_TYPE.get(emoji, "hint"),
        message=message,
        emoji=emoji,
    )


def _split_emoji_prefix(text: str) -> tuple[str, str]:
    """
    Peel off the leading emoji token if present, returning
    ``(emoji, rest)``. When the string does not start with one of
    the known emoji, ``emoji`` is empty and ``rest`` is the whole
    stripped string.
    """
    for candidate in _EMOJI_TO_TYPE:
        if text.startswith(candidate):
            return candidate, text[len(candidate):].strip()
    return "", text.strip()


def _bullet_list(items: list[str]) -> str:
    """
    Render a list of strings as a compact ``- item`` block. Empty
    inputs render as ``(nenhum)`` so the model does not confuse an
    empty section with a missing one.
    """
    if not items:
        return "(nenhum)"
    return "\n".join(f"- {item}" for item in items)


def _recent_actions(transcript: SessionTranscript, limit: int = 5) -> list[str]:
    """
    Extract the last ``limit`` action-turn labels from the
    transcript. Action turns carry a JSON payload — we peel the
    ``label`` field when parseable, else fall back to the raw string.
    """
    import json

    actions: list[str] = []
    for turn in transcript.turns:
        if turn.speaker != "action":
            continue
        try:
            payload = json.loads(turn.content)
            label = payload.get("label") if isinstance(payload, dict) else None
        except (ValueError, TypeError):
            label = None
        actions.append(str(label or turn.content))
    return actions[-limit:]


def _recent_persona_snippets(
    transcript: SessionTranscript,
    limit: int = 4,
) -> list[str]:
    """
    Return short snippets from the last few persona replies so the
    coach knows what the citizen has said recently. We keep each
    snippet under 120 characters to bound the prompt size.
    """
    snippets: list[str] = []
    for turn in transcript.turns:
        if turn.speaker != "persona":
            continue
        text = turn.content.strip().replace("\n", " ")
        if len(text) > 120:
            text = text[:117].rstrip() + "..."
        snippets.append(text)
    return snippets[-limit:]


def _format_transcript(transcript: SessionTranscript, limit: int = 8) -> str:
    """
    Render the tail of the transcript as an ``ATTENDANT / CITIZEN``
    dialogue block. We keep only the last ``limit`` speech turns so
    the coach never has to reason over an entire long session — the
    latest exchanges are what matter for a next-move hint.
    """
    lines: list[str] = []
    speech_turns = [t for t in transcript.turns if t.speaker in {"agent", "persona"}]
    for turn in speech_turns[-limit:]:
        role = "ATENDENTE" if turn.speaker == "agent" else "CIDADÃO"
        lines.append(f"{role}: {turn.content.strip()}")
    if not lines:
        return "(transcript vazio; sugira o primeiro movimento)"
    return "\n".join(lines)


__all__ = [
    "Coach",
    "CoachSuggestion",
    "CoachSuggestionType",
]
