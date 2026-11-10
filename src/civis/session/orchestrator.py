"""
Session orchestrator — the turn loop of a CIVIS training session.

Responsibilities:
    1. Advance the FSM one step per incoming agent turn.
    2. Assemble the persona prompt from the current PersonaState +
       transcript history + selectively-retrieved facts (B.5).
    3. Call the persona LLM provider and record its reply as a persona
       turn in the transcript.
    4. Detect which scenario facts were disclosed in the persona reply
       and update state.revealed_fact_keys.
    5. Emit an observable TurnEvent per turn (both for the agent and
       the persona reply), so the contradiction detector (B.4) and other
       downstream analysers can walk the session without re-parsing the
       transcript.
    6. (Phase D) Expose the LLMResponse of every persona turn on the
       returned TurnResult so the CLI can persist per-turn telemetry
       (input/output tokens, latency, provider name) for the M4
       metrics panel.
    7. (Phase D++) Offer a streaming variant, run_agent_turn_streaming,
       that yields persona tokens as they arrive and exposes the fully
       reconstructed TurnResult via ``last_result`` once the stream
       drains. The Streamlit chat page pipes the generator into
       ``st.write_stream`` to render the answer token-by-token.

Design notes:
    - The orchestrator does NOT own the LLM provider — it receives one
      via the constructor. Tests inject a FakePersonaProvider; the CLI
      wires the real Ollama/Anthropic/OpenAI-compat provider.
    - The FSM engine is called with the FRESH state (post-agent turn,
      pre-persona reply); this matches the acceptance criterion in
      A.2 where advance_turn happens between input and prompt.
    - Fact detection has two parts:
        (a) SUBSTRING MATCH of the canonical fact value in the persona
            reply — this is what marks a fact as "revealed";
        (b) KEYWORD-TRIGGERED OBSERVATION: when the agent's last message
            contains a fact's retrieval_keywords, we record the persona
            reply as the "observed value" for that fact_key. The
            contradiction detector compares observed values across turns.
    - (Phase D+++) Action turns (speaker=="action") are recorded in the
      transcript by the web layer but STRIPPED here before the history
      reaches the persona prompt — the LLM must never see a JSON action
      payload as if it were user speech.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from pydantic import BaseModel

from civis.fsm.engine import advance_turn
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.personas.base import PersonaState
from civis.prompts.fact_retrieval import fact_keys_matched_by_agent_message
from civis.prompts.persona import build_persona_prompt
from civis.session.fact_matching import fact_value_appears_in_reply
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript, Turn
from civis.session.turn_events import TurnEvent


class TurnResult(BaseModel):
    """
    What a single agent-turn produced: the transcript entries and the
    FSM state after both turns landed.
    """

    agent_turn: Turn
    persona_reply: Turn
    state_after: PersonaState
    newly_revealed_fact_keys: list[str]
    # Fact keys the last agent message was asking about (via retrieval
    # keywords). The persona reply is treated as the OBSERVED VALUE for
    # each of these keys — the contradiction detector uses that mapping.
    matched_fact_keys: list[str] = []
    # Phase D: expose the raw LLMResponse so the CLI can persist per-turn
    # telemetry (tokens, latency, provider name). Optional — tests that
    # only check FSM behaviour don't need to inspect it.
    llm_response: LLMResponse | None = None


@dataclass
class SessionOrchestrator:
    """
    Stateful orchestrator holding the current PersonaState, transcript
    and provider. One instance per live session.

    Also collects an observable event stream in `turn_events`, appended
    to on every agent + persona turn. Downstream analysers (contradiction
    detector in B.4) walk this stream instead of re-parsing the on-disk
    transcript.

    Phase D++: ``last_result`` holds the TurnResult of the most recent
    streaming turn. It is populated only by ``run_agent_turn_streaming``
    once the generator drains, so the Streamlit page can persist telemetry
    after ``st.write_stream`` returns.
    """

    scenario: ScenarioFile
    persona_provider: LLMProvider
    transcript: SessionTranscript
    state: PersonaState
    turn_events: list[TurnEvent] = field(default_factory=list)
    last_result: TurnResult | None = None

    def run_agent_turn(self, agent_message: str) -> TurnResult:
        """
        Ingest one message from the agent, advance the FSM, call the
        persona provider, and record both turns in the transcript.
        """
        # 1. Record the agent turn first so history is chronological on
        #    disk even if the LLM call fails mid-way.
        agent_turn = self.transcript.append("agent", agent_message)
        self._emit_turn_event(
            turn_index=agent_turn.turn_index,
            speaker="agent",
            content=agent_message,
            newly_revealed_fact_keys=[],
            observed_fact_values={},
        )

        # 2. Advance the FSM. This mutates our local state reference (via
        #    reassignment) but the transcript stays the source of truth
        #    for what actually happened.
        self.state = advance_turn(self.state)

        # 3. Assemble the persona prompt from the CURRENT state and the
        #    transcript BEFORE we've appended the persona reply.
        history = _transcript_history(self.transcript, exclude_last=True)
        system_prompt, user_prompt = build_persona_prompt(
            state=self.state,
            history=history,
            last_agent_message=agent_message,
        )

        # 4. Call the persona LLM. Errors bubble up; the caller (CLI)
        #    decides whether to retry or abort the session.
        response = self.persona_provider.complete([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ])

        # 5. Record the persona reply and detect (a) newly-revealed facts
        #    by substring match, and (b) which fact_keys the agent was
        #    asking about via keyword-triggered retrieval. Both feed the
        #    TurnEvent stream.
        persona_turn = self.transcript.append("persona", response.content)
        newly_revealed = self._absorb_revealed_facts(
            response.content,
            last_agent_message=agent_message,
        )
        matched_keys = fact_keys_matched_by_agent_message(
            facts=self.scenario.persona.facts,
            last_agent_message=agent_message,
        )
        observed_fact_values = {key: response.content for key in matched_keys}
        self._emit_turn_event(
            turn_index=persona_turn.turn_index,
            speaker="persona",
            content=response.content,
            newly_revealed_fact_keys=newly_revealed,
            observed_fact_values=observed_fact_values,
        )

        return TurnResult(
            agent_turn=agent_turn,
            persona_reply=persona_turn,
            state_after=self.state,
            newly_revealed_fact_keys=newly_revealed,
            matched_fact_keys=matched_keys,
            llm_response=response,
        )

    def run_agent_turn_streaming(
        self, agent_message: str
    ) -> Iterator[str]:
        """
        Streaming variant of :meth:`run_agent_turn`.

        Yields persona tokens as they arrive from ``persona_provider.stream``.
        The final aggregated :class:`TurnResult` (persona turn, revealed
        facts, matched keys, LLMResponse) is stored on ``self.last_result``
        once the generator is fully drained — callers read that attribute
        after ``st.write_stream`` returns, then persist transcript /
        telemetry as usual.

        Ordering matters:
            - agent turn + agent TurnEvent are recorded BEFORE the LLM call
              so the on-disk transcript still holds the trainee's input
              even if the stream aborts mid-way.
            - FSM is advanced BEFORE the prompt is built (same rule as the
              non-streaming path).
            - The persona turn is only appended to the transcript AFTER
              the stream drains and the full text is known.
        """
        # Reset last_result up front so a stale value from a previous turn
        # can't fool the caller if this stream aborts mid-way. It becomes
        # meaningful again only when the sentinel below fires.
        self.last_result = None

        # 1. Record the agent turn (same as run_agent_turn).
        agent_turn = self.transcript.append("agent", agent_message)
        self._emit_turn_event(
            turn_index=agent_turn.turn_index,
            speaker="agent",
            content=agent_message,
            newly_revealed_fact_keys=[],
            observed_fact_values={},
        )

        # 2. Advance FSM before building the prompt.
        self.state = advance_turn(self.state)

        # 3. Build the prompt from the transcript minus the freshest agent
        #    turn (rendered separately inside <user_input> in the template).
        history = _transcript_history(self.transcript, exclude_last=True)
        system_prompt, user_prompt = build_persona_prompt(
            state=self.state,
            history=history,
            last_agent_message=agent_message,
        )

        # 4. Consume the stream. Content pieces are yielded to the caller
        #    as they arrive; the final chunk carries the aggregated
        #    LLMResponse so we can rebuild TurnResult.
        content_parts: list[str] = []
        final_response: LLMResponse | None = None
        for chunk in self.persona_provider.stream([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]):
            if chunk.content_delta:
                content_parts.append(chunk.content_delta)
                yield chunk.content_delta
            if chunk.is_final:
                final_response = chunk.final_response

        # 5. Persist the persona turn only after the full text is known.
        #    Fallback for providers whose default stream() didn't populate
        #    final_response: synthesise a zero-telemetry LLMResponse from
        #    the aggregated text so downstream code (which expects
        #    llm_response to exist) still works. Real providers always
        #    fill final_response.
        full_text = "".join(content_parts)
        if final_response is None:
            final_response = LLMResponse(
                content=full_text,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                provider_name=self.persona_provider.name,
            )

        persona_turn = self.transcript.append("persona", full_text)
        newly_revealed = self._absorb_revealed_facts(
            full_text,
            last_agent_message=agent_message,
        )
        matched_keys = fact_keys_matched_by_agent_message(
            facts=self.scenario.persona.facts,
            last_agent_message=agent_message,
        )
        observed_fact_values = {key: full_text for key in matched_keys}
        self._emit_turn_event(
            turn_index=persona_turn.turn_index,
            speaker="persona",
            content=full_text,
            newly_revealed_fact_keys=newly_revealed,
            observed_fact_values=observed_fact_values,
        )

        # 6. Expose the reconstructed TurnResult so the caller can persist
        #    telemetry after the generator drains.
        self.last_result = TurnResult(
            agent_turn=agent_turn,
            persona_reply=persona_turn,
            state_after=self.state,
            newly_revealed_fact_keys=newly_revealed,
            matched_fact_keys=matched_keys,
            llm_response=final_response,
        )

    def _absorb_revealed_facts(
        self,
        persona_reply: str,
        last_agent_message: str | None,
    ) -> list[str]:
        """
        Update state.revealed_fact_keys with any scenario fact whose value
        appears (via the flexible matcher) in the persona reply, and
        return the list of keys that transitioned from 'not revealed' to
        'revealed' on THIS turn.

        The matcher (session.fact_matching.fact_value_appears_in_reply)
        is deliberately tolerant: it strips diacritics/case/punctuation,
        expands date values to their common numeric/textual variants,
        and falls back to multi-word overlap for names/addresses. This
        is what lets "12/03/1954", "12 de março de 1954" and "doze de
        março de 1954" all satisfy a birth_date fact — the original
        literal-substring matcher failed on the very first thing users
        try.

        Secret facts (is_secret=True) never get auto-added here — leaking
        a secret is the exact adversarial condition fase C measures, and
        we don't want to silently promote it to 'legitimately revealed'.

        `last_agent_message` is accepted for parity with the rest of the
        keyword-driven pipeline but is not used here: revelation is judged
        strictly by the reply's content. Passing None is valid (e.g. when
        replaying a transcript at session-resume time).
        """
        del last_agent_message  # currently unused; kept for API symmetry

        already = self.state.revealed_fact_keys
        newly: list[str] = []

        for fact in self.scenario.persona.facts:
            if fact.is_secret:
                continue
            if fact.key in already:
                continue
            if fact_value_appears_in_reply(
                fact_value=fact.value,
                reply=persona_reply,
                revealed_patterns=fact.revealed_patterns or None,
            ):
                newly.append(fact.key)

        if newly:
            self.state = self.state.model_copy(
                update={"revealed_fact_keys": already | set(newly)}
            )
        return newly

    def _emit_turn_event(
        self,
        turn_index: int,
        speaker: str,
        content: str,
        newly_revealed_fact_keys: list[str],
        observed_fact_values: dict[str, str],
    ) -> None:
        """Append one TurnEvent to the observable stream."""
        self.turn_events.append(
            TurnEvent(
                turn_index=turn_index,
                speaker=speaker,
                content=content,
                newly_revealed_fact_keys=newly_revealed_fact_keys,
                observed_fact_values=observed_fact_values,
            )
        )


def _transcript_history(
    transcript: SessionTranscript,
    exclude_last: bool,
) -> list[tuple[str, str]]:
    """
    Convert the on-disk transcript into the (speaker, content) tuple
    list the prompt builder expects. When exclude_last=True we drop the
    freshest agent turn (we're about to render it separately inside
    <user_input> in the user prompt).

    Phase D+++ (original policy): turns with ``speaker == "action"`` were
    STRIPPED here so the persona LLM never sees a JSON action payload as
    if it were user speech.

    Onda 4 F1 (2026-09-29 bug fix): the strip-outright policy broke the
    fiction — after the atendente clicked "Emitir certidão" and the UI
    printed the document card, the persona had no idea anything had
    happened and would ask again for the same thing. Now action turns
    are SUMMARISED into a natural-language stage direction attributed to
    the atendente, so the persona LLM understands the action landed. The
    raw JSON payload never reaches the prompt — only a short human line.

    Queue turns (``speaker == "queue"``) stay filtered by design: a
    citizen doesn't "hear" the queue getting longer, that pressure signal
    lives in the FSM, not in the chat.
    """
    turns = transcript.turns[:-1] if exclude_last else transcript.turns
    rendered: list[tuple[str, str]] = []
    for t in turns:
        if t.speaker in ("agent", "persona"):
            rendered.append((t.speaker, t.content))
            continue
        if t.speaker == "action":
            summary = _summarise_action_for_prompt(t.content)
            if summary:
                # Attributed to the atendente in the transcript stream so
                # the persona reads it as "the servidor did this now".
                rendered.append(("agent", summary))
    return rendered


# Match a leading emoji-like glyph plus optional trailing whitespace, e.g.
# "📋 Explicar procedimento" → "Explicar procedimento". Kept intentionally
# broad (any non-word/non-space char sequence at the start) so we handle
# emojis, arrows and ornament chars without a full unicode-emoji table.
_LEADING_ORNAMENT_RE = re.compile(r"^[^\w\s]+\s*")


def _summarise_action_for_prompt(payload_json: str) -> str | None:
    """
    Turn an action-turn JSON payload into a short pt-BR stage direction
    the persona LLM can read as "the atendente just did this in front
    of you". Returns None when the payload is malformed — the caller
    then drops the turn entirely rather than surface garbage.

    Format examples:
        no document  →  "*executa a ação: Explicar procedimento*"
        w/ document  →  "*emite e entrega o documento 'Segunda via da
                          certidão de nascimento'*"

    Wrapping the line in asterisks is the well-known chat/RPG stage-
    direction convention — LLMs parse it as "action, not speech" without
    us needing an explicit meta-instruction.
    """
    try:
        payload = json.loads(payload_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    raw_label = payload.get("label") or payload.get("action_id") or "ação"
    label = _LEADING_ORNAMENT_RE.sub("", str(raw_label)).strip() or "ação"

    document = payload.get("document")
    if isinstance(document, dict):
        title = str(document.get("title") or "").strip()
        if title:
            return f"*emite e entrega o documento '{title}'*"
        return f"*emite e entrega um documento ({label})*"

    return f"*executa a ação: {label}*"
