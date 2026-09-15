"""
Mock LLM providers for offline adversarial runs.

Two shapes:

    RecordingMockProvider   Scripted or callable replies + captured prompts.
                            Used by the battery runner in tests and by the
                            CLI when no real backend is configured.

    ScriptedReplyMap        Convenience factory: dict {attack_id_or_key:
                            reply} → RecordingMockProvider.

Neither module ever imports httpx or opens a socket. Real providers live
in civis.llm.*_provider.
"""

from collections.abc import Callable, Mapping

from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse


class RecordingMockProvider(LLMProvider):
    """
    Test-friendly provider.

    Given a `reply_fn(messages) -> str`, returns that string on every call
    and records the (system, user) tuple. Callers inspect `captured_prompts`
    afterwards to assert on prompt shape.

    A convenience constructor accepts a list of replies and cycles through
    them: the first `complete()` call returns replies[0], the second
    replies[1], and so on. When the list is exhausted the last reply is
    repeated — that way tests don't crash on off-by-one.
    """

    def __init__(
        self,
        reply_fn: Callable[[list[LLMMessage]], str] | None = None,
        replies: list[str] | None = None,
        name: str = "mock:recording",
    ) -> None:
        if reply_fn is None and replies is None:
            raise ValueError(
                "RecordingMockProvider requires either reply_fn or replies."
            )
        if reply_fn is not None and replies is not None:
            raise ValueError(
                "RecordingMockProvider takes either reply_fn or replies, not both."
            )

        if replies is not None:
            self._replies = list(replies)
            self._calls = 0
            self._reply_fn = self._script_reply
        else:
            assert reply_fn is not None  # narrowing for mypy/pyright
            self._reply_fn = reply_fn
            self._replies = None
            self._calls = 0

        self._name = name
        self.captured_prompts: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        self.captured_prompts.append((system, user))
        content = self._reply_fn(messages)
        self._calls += 1
        return LLMResponse(
            content=content,
            # Tokens/latency are fabricated but non-zero so downstream code
            # doing arithmetic doesn't hit division-by-zero.
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self._name,
        )

    def _script_reply(self, _messages: list[LLMMessage]) -> str:
        """Cycle through the scripted list; repeat the last on overflow."""
        assert self._replies is not None
        if not self._replies:
            return ""
        if self._calls < len(self._replies):
            return self._replies[self._calls]
        return self._replies[-1]


def build_keyword_mock(
    keyword_to_reply: Mapping[str, str],
    default_reply: str = "Não posso ajudar com isso.",
    name: str = "mock:keyword",
) -> RecordingMockProvider:
    """
    Build a provider that returns a reply based on which keyword hits the
    incoming user message. First match wins; falls back to `default_reply`.

    Used to script targeted "vulnerable" behaviour for individual attacks
    in tests without maintaining a giant scripted list.
    """
    lowered = {k.lower(): v for k, v in keyword_to_reply.items()}

    def _reply(messages: list[LLMMessage]) -> str:
        user = next((m.content for m in messages if m.role == "user"), "")
        user_lower = user.lower()
        for keyword, reply in lowered.items():
            if keyword in user_lower:
                return reply
        return default_reply

    return RecordingMockProvider(reply_fn=_reply, name=name)
