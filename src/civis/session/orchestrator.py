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
"""

from dataclasses import dataclass, field

from pydantic import BaseModel

from civis.fsm.engine import advance_turn
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.personas.base import PersonaState
from civis.prompts.fact_retrieval import fact_keys_matched_by_agent_message
from civis.prompts.persona import build_persona_prompt
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
    """

    scenario: ScenarioFile
    persona_provider: LLMProvider
    transcript: SessionTranscript
    state: PersonaState
    turn_events: list[TurnEvent] = field(default_factory=list)

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

    def _absorb_revealed_facts(
        self,
        persona_reply: str,
        last_agent_message: str | None,
    ) -> list[str]:
        """
        Update state.revealed_fact_keys with any scenario fact whose value
        appears (case-insensitive) in the persona reply, and return the
        list of keys that transitioned from 'not revealed' to 'revealed'
        on THIS turn.

        Secret facts (is_secret=True) never get auto-added here — leaking
        a secret is the exact adversarial condition fase C measures, and
        we don't want to silently promote it to 'legitimately revealed'.

        `last_agent_message` is accepted for parity with the rest of the
        keyword-driven pipeline but is not used here: revelation is judged
        strictly by the reply's content. Passing None is valid (e.g. when
        replaying a transcript at session-resume time).
        """
        del last_agent_message  # currently unused; kept for API symmetry

        reply_lower = persona_reply.lower()
        already = self.state.revealed_fact_keys
        newly: list[str] = []

        for fact in self.scenario.persona.facts:
            if fact.is_secret:
                continue
            if fact.key in already:
                continue
            if fact.value.lower() in reply_lower:
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
    """
    turns = transcript.turns[:-1] if exclude_last else transcript.turns
    return [(t.speaker, t.content) for t in turns]
