"""
FSM state enumerations for CIVIS personas.

The FSM controls WHAT the persona does (phase progression + emotional escalation).
The LLM controls HOW the persona speaks (interpretation of the current state).
This separation is the core design choice: the script is auditable, the language is not.
"""

from enum import StrEnum


class Phase(StrEnum):
    """
    High-level phase of a service interaction, from the persona's perspective.

    OPENING          - persona arrives and states an initial demand
    INFO_GATHERING   - persona answers / evades / confuses while agent gathers data
    ATTEMPT          - persona pushes for its goal (legitimate request or fraud attempt)
    RESOLUTION       - interaction closes (success, refusal, or timeout)
    """

    OPENING = "opening"
    INFO_GATHERING = "info_gathering"
    ATTEMPT = "attempt"
    RESOLUTION = "resolution"


class EmotionalState(StrEnum):
    """
    Emotional register the persona is currently expressing.

    Intensity roughly increases from CALM to ANGRY along the frustration axis.
    MANIPULATIVE is orthogonal: used by the fraudster profile to signal
    deliberate emotional pressure (urgency, false authority) rather than genuine feeling.
    """

    CALM = "calm"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    DESPERATE = "desperate"
    MANIPULATIVE = "manipulative"
