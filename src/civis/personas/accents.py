"""
Regional accent catalog for personas.

Adds a *purely optional* dimension to a PersonaProfile: which Brazilian
regional accent the character speaks with. When a scenario declares one,
the persona prompt gains a `# Sotaque` block that steers the LLM toward
region-specific slang and phonetics; when it does not, the prompt is
byte-identical to the pre-accent version — the field is opt-in on purpose
so shipping scenarios do not silently change behaviour.

Design notes:

    - StrEnum values are lower-snake_case region ids so they survive YAML
      round-trips as bare strings ("nordeste" not "RegionalAccent.NORDESTE").
    - The enum is intentionally coarse (one entry per macro-region, with
      three splits for Sudeste because SP/RJ/MG accents are mutually
      unintelligible to Brazilians as identity markers). Finer-grained
      city-level accents belong in a future extension, not here.
    - The catalog lives next to PersonaProfile so scenario loading only
      needs one import surface for persona-shaped data.
"""

from enum import StrEnum


class RegionalAccent(StrEnum):
    """
    Brazilian regional accents the persona LLM can adopt.

    Chosen for pitch value: five of these carry immediately recognisable
    slang ("ôxente", "bah", "mano", "caraca", "uai") that lets an
    investor watching the demo *hear* that the product is Brazilian, not
    a US wrapper with a pt-BR label.
    """

    # Nordeste — pan-regional slang cluster (BA/PE/CE/PB/RN etc.).
    NORDESTE = "nordeste"
    # Sul — gaúcho / catarinense cluster.
    SUL = "sul"
    # Sudeste, split into three because the accents mark identity strongly.
    SUDESTE_SP = "sudeste_sp"
    SUDESTE_RJ = "sudeste_rj"
    SUDESTE_MG = "sudeste_mg"
    # Norte — paraense / amazonense cluster.
    NORTE = "norte"
    # Centro-Oeste — goiano / mato-grossense cluster.
    CENTRO_OESTE = "centro_oeste"
