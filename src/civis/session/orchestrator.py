"""
Session orchestrator — the turn loop of a CIVIS training session.

Responsibilities:
    1. Advance the FSM one step per incoming agent turn.
    2. Assemble the persona prompt from the current PersonaState +
       transcript history + revealed facts.
    3. Call the persona LLM provider and record its reply as a persona
       turn in the transcript.
    4. Detect which scenario facts were disclosed in the persona reply
       and update state.revealed_fact_keys — this is what makes fact
       retrieval selective and stops the same fact from being 'newly
       revealed' twice.

Design notes:
    - The orchestrator does NOT own the LLM provider — it receives one
      via the constructor. Tests inject a FakePersonaProvider; the CLI
      wires the real Ollama/Anthropic/OpenAI-compat provider.
    - The FSM engine is called with the FRESH state (post-agent turn,
      pre-persona reply); this matches the acceptance criterion in
      A.2 where advance_turn happens between input and prompt.
    - Fact detection is a case-insensitive substring match against the
      value of each fact. Good enough for fase A; fase B replaces it
      with an explicit fact-retrieval keyword table.

Usage:
    orchestrator = SessionOrchestrator(
        scenario=scenario,
        persona_provider=provider,
        transcript=SessionTranscript(session_id=...),
        state=PersonaState(profile=scenario.persona, ...),
    )
    turn = orchestrator.run_agent_turn("Bom dia, em que posso ajudar?")
    print(turn.persona_reply.content)
"""

from dataclasses import dataclass

from pydantic import BaseModel

from civis.fsm.engine import advance_turn
from civis.llm.provider import LLMMessage, LLMProvider
from civis.personas.base import PersonaState
from civis.prompts.persona import build_persona_prompt
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript, Turn


class TurnResult(BaseModel):
    """
    What a single agent-turn produced: the transcript entries and the
    FSM state after both turns landed.
    """

    agent_turn: Turn
    persona_reply: Turn
    state_after: PersonaState
    newly_revealed_fact_keys: list[str]


@dataclass
class SessionOrchestrator:
    """
    Stateful orchestrator holding the current PersonaState, transcript
    and provider. One instance per live session.
    """

    scenario: ScenarioFile
    persona_provider: LLMProvider
    transcript: SessionTranscript
    state: PersonaState

    def run_agent_turn(self, agent_message: str) -> TurnResult:
        """
        Ingest one message from the agent, advance the FSM, call the
        persona provider, and record both turns in the transcript.
        """
        # 1. Record the agent turn first so history is chronological on
        #    disk even if the LLM call fails mid-way.
        agent_turn = self.transcript.append("agent", agent_message)

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

        # 5. Record the persona reply and detect newly-revealed facts.
        persona_turn = self.transcript.append("persona", response.content)
        newly_revealed = self._absorb_revealed_facts(response.content)

        return TurnResult(
            agent_turn=agent_turn,
            persona_reply=persona_turn,
            state_after=self.state,
            newly_revealed_fact_keys=newly_revealed,
        )

    def _absorb_revealed_facts(self, persona_reply: str) -> list[str]:
        """
        Update state.revealed_fact_keys with any scenario fact whose value
        appears (case-insensitive) in the persona reply, and return the
        list of keys that transitioned from 'not revealed' to 'revealed'
        on THIS turn.

        Secret facts (is_secret=True) never get auto-added here — leaking
        a secret is the exact adversarial condition fase C measures, and
        we don't want to silently promote it to 'legitimately revealed'.
        """
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
