"""
Custom Faker providers for the Brazilian civil-registry domain.

All generated documents are DELIBERATELY FICTIONAL and carry the "FIC-" prefix
so they cannot be confused with real Brazilian documents (CPF, RG, birth
certificates). This is stronger than generating structurally valid IDs and
matches the plan's requirement of zero re-identification risk (LGPD).
"""

from datetime import date, timedelta

from faker.providers import BaseProvider

# Prefix that marks every generated document as fictional.
# A real system would reject anything starting with this prefix.
FICTIONAL_PREFIX = "FIC"

# Bounds for numeric suffixes on fictional documents.
DOC_SUFFIX_MIN = 100_000
DOC_SUFFIX_MAX = 999_999

# Age range for civil events (birth, marriage): 1 to 70 years ago.
CIVIL_EVENT_MIN_DAYS_AGO = 365
CIVIL_EVENT_MAX_DAYS_AGO = 365 * 70

# Year range for fictional birth certificates.
BIRTH_YEAR_MIN = 1950
BIRTH_YEAR_MAX = 2020


class FictionalCivilRegistryProvider(BaseProvider):
    """
    Faker provider that generates unmistakably-fake civil-registry data.

    Usage:
        fake = Faker("pt_BR")
        fake.add_provider(FictionalCivilRegistryProvider)
        fake.fictional_cpf()  # -> "FIC-CPF-847263"
    """

    def fictional_cpf(self) -> str:
        return f"{FICTIONAL_PREFIX}-CPF-{self.generator.random_int(DOC_SUFFIX_MIN, DOC_SUFFIX_MAX)}"

    def fictional_rg(self) -> str:
        return f"{FICTIONAL_PREFIX}-RG-{self.generator.random_int(DOC_SUFFIX_MIN, DOC_SUFFIX_MAX)}"

    def fictional_birth_certificate_id(self) -> str:
        year = self.generator.random_int(BIRTH_YEAR_MIN, BIRTH_YEAR_MAX)
        serial = self.generator.random_int(DOC_SUFFIX_MIN, DOC_SUFFIX_MAX)
        return f"{FICTIONAL_PREFIX}-NASC-{year}-{serial}"

    def fictional_civil_event_date(self) -> date:
        days_ago = self.generator.random_int(CIVIL_EVENT_MIN_DAYS_AGO, CIVIL_EVENT_MAX_DAYS_AGO)
        return date.today() - timedelta(days=days_ago)
