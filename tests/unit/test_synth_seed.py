"""
Determinism tests for synthetic-base generation.

Same seed -> byte-identical output. Hard requirement of O6 (reproducibility),
enforced at CI level so that any regression in the Faker providers is caught
before merge.
"""

from civis.synth.generate import generate_base

TEST_SEED = 42
ALTERNATE_SEED = 43
SAMPLE_COUNT = 5


def test_same_seed_produces_same_base():
    first = generate_base(seed=TEST_SEED, count=SAMPLE_COUNT)
    second = generate_base(seed=TEST_SEED, count=SAMPLE_COUNT)
    assert first == second


def test_different_seeds_produce_different_bases():
    with_seed_a = generate_base(seed=TEST_SEED, count=SAMPLE_COUNT)
    with_seed_b = generate_base(seed=ALTERNATE_SEED, count=SAMPLE_COUNT)
    assert with_seed_a != with_seed_b


def test_all_documents_carry_fictional_prefix():
    """
    Every generated document must carry the FIC- prefix — no structurally
    valid Brazilian IDs are ever emitted. This is a zero-re-identification
    guarantee (see registry_providers.py rationale).
    """
    base = generate_base(seed=TEST_SEED, count=SAMPLE_COUNT)
    for citizen in base:
        assert citizen["cpf"].startswith("FIC-")
        assert citizen["rg"].startswith("FIC-")
        assert citizen["birth_certificate_id"].startswith("FIC-")
