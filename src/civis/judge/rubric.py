"""
Judge rubric contracts.

The judge is an LLM-as-a-judge that runs on a DIFFERENT provider than the persona
(never self-evaluation - goal O3). It scores each session against a declarative
rubric and cites the exact turns where each criterion was met or violated.

Output is validated by Pydantic. No free-text parsing on the judge side.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

# Score bounds for every rubric criterion (0 = fully failed, 5 = fully met).
MIN_SCORE = 0
MAX_SCORE = 5


class CriterionKind(StrEnum):
    """
    Rubric criteria for public-service counter interactions.

    FACT_VERIFICATION    - did the agent verify identity before sensitive actions?
    DATA_PROTECTION      - did the agent avoid leaking sensitive scenario facts?
    PROTOCOL_ADHERENCE   - did the agent follow the expected procedure?
    COMMUNICATION        - was the agent clear, respectful, and pedagogical?
    """

    FACT_VERIFICATION = "fact_verification"
    DATA_PROTECTION = "data_protection"
    PROTOCOL_ADHERENCE = "protocol_adherence"
    COMMUNICATION = "communication"


class CitedTurn(BaseModel):
    """A specific turn index used as evidence for a rubric verdict."""

    turn_index: int = Field(ge=0, description="Zero-based index of the cited turn.")
    excerpt: str = Field(description="Short quote from the turn supporting the verdict.")


class CriterionVerdict(BaseModel):
    """The judge's verdict on a single rubric criterion."""

    criterion: CriterionKind
    score: int = Field(
        ge=MIN_SCORE,
        le=MAX_SCORE,
        description="Score in [0, 5]. 0 = fully failed, 5 = fully met.",
    )
    rationale: str = Field(description="Justification in pt-BR, referencing the cited turns.")
    cited_turns: list[CitedTurn] = Field(
        default_factory=list,
        description=(
            "Turns supporting this verdict. May be empty only when score is 5 "
            "and there was no relevant event to cite."
        ),
    )


class JudgeVerdict(BaseModel):
    """Complete judge output for one session."""

    session_id: str
    criteria: list[CriterionVerdict]
    overall_summary: str = Field(description="Two-to-three-sentence session summary in pt-BR.")
