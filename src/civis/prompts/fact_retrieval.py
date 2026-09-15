"""
Selective fact retrieval (B.5).

Given the last agent message plus the current PersonaState, decide which
scenario facts should surface in the persona prompt on this turn.

Two triggers, combined with OR:
    (1) The fact has already been revealed on a previous turn. Facts stay
        visible so the persona doesn't contradict itself by "forgetting"
        what it already said.
    (2) The last agent message contains one of the fact's
        retrieval_keywords (case-insensitive, whole-substring match).
        This is the semantic trigger — the fact only shows up when the
        agent asks something related.

Fallback: if the retrieval produces NO facts and none were revealed
before, the persona still receives its background + goal + recent
history via the ordinary prompt sections. That keeps the persona
answering something coherent even when the agent hasn't asked anything
specific yet (opening turns, small talk, generic prompts).

Secret facts (is_secret=True) are always available to the prompt
builder — but the builder places them under a "never volunteer" heading
regardless of trigger. Retrieval decides visibility, not disclosure
policy.
"""

from civis.personas.base import PersonaFact


def select_facts_for_prompt(
    facts: list[PersonaFact],
    revealed_fact_keys: set[str],
    last_agent_message: str | None,
) -> list[PersonaFact]:
    """
    Return the subset of facts that should surface in the persona prompt
    this turn.

    Selection rule (OR of both):
        - fact.key in revealed_fact_keys, OR
        - any keyword in fact.retrieval_keywords appears (case-insensitive)
          inside last_agent_message.

    Secrets are always included. They appear under a "never volunteer"
    heading in the prompt builder, but keeping them in the returned list
    lets the persona *know* what to hide.

    Facts with an empty retrieval_keywords list AND not yet revealed AND
    not secret are excluded — this is the selectivity that stops the
    persona from spilling every scenario fact at once.
    """
    haystack = (last_agent_message or "").lower()
    selected: list[PersonaFact] = []
    for fact in facts:
        if fact.is_secret:
            selected.append(fact)
            continue
        if fact.key in revealed_fact_keys:
            selected.append(fact)
            continue
        if _any_keyword_hits(fact.retrieval_keywords, haystack):
            selected.append(fact)
            continue
    return selected


def fact_keys_matched_by_agent_message(
    facts: list[PersonaFact],
    last_agent_message: str | None,
) -> list[str]:
    """
    Return the ordered list of fact.key values whose retrieval keywords
    hit the last agent message. Used by the orchestrator to decide which
    fact_keys to record as "observed values" for the contradiction
    detector (B.4).

    Secrets are excluded — a secret fact should never be logged as
    'observed' via keyword; that would let a fraudster manipulate the
    detector by parroting the honeytoken's keywords.
    """
    haystack = (last_agent_message or "").lower()
    return [
        fact.key
        for fact in facts
        if not fact.is_secret and _any_keyword_hits(fact.retrieval_keywords, haystack)
    ]


# ---- helpers ---------------------------------------------------------------

def _any_keyword_hits(keywords: list[str], haystack_lower: str) -> bool:
    """
    True if any keyword appears as a substring in the (already lowercased)
    haystack. Empty keywords list returns False — a fact without
    retrieval_keywords is only accessible via the "already revealed" path.
    """
    if not keywords:
        return False
    return any(kw.lower() in haystack_lower for kw in keywords if kw.strip())
