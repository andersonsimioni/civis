"""
Configuration data contracts (model catalog + role assignments).

Design: the user declares a CATALOG of LLM entries (each pinned to a
provider + model id + endpoint) and then maps ROLES (persona, judge)
to catalog entries by name. Swapping the model behind a role is a
one-line change to config.toml.

This decouples "which models are available" from "who uses which model",
so experiments (e.g. try Claude as the judge for one session) require
no code changes.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ProviderKind(StrEnum):
    """
    Supported provider families.

    OLLAMA           Local HTTP server (default: http://localhost:11434).
    OPENAI_COMPAT    Any service speaking OpenAI /v1/chat/completions.
                     One adapter covers OpenAI, Groq, DeepSeek, Together,
                     xAI, Fireworks, Mistral, and Ollama's /v1 endpoint.
    ANTHROPIC        Claude via the Anthropic SDK (distinct wire format).
    """

    OLLAMA = "ollama"
    OPENAI_COMPAT = "openai_compat"
    ANTHROPIC = "anthropic"


# Default blocking timeout for a single completion call, in seconds.
DEFAULT_REQUEST_TIMEOUT_S = 60.0


class ModelEntry(BaseModel):
    """
    One entry in the model catalog. Identified externally by its TOML key
    (see CivisConfig.models). Roles reference entries by that key.
    """

    provider: ProviderKind
    model_id: str = Field(
        description=(
            "Provider-specific model name "
            "(e.g. 'qwen2.5:7b-instruct-q4_K_M', 'gpt-4o', 'claude-sonnet-4-6')."
        ),
    )
    base_url: str | None = Field(
        default=None,
        description=(
            "HTTP endpoint. Required for OLLAMA and OPENAI_COMPAT. "
            "Ignored for ANTHROPIC (SDK handles routing)."
        ),
    )
    api_key_env: str | None = Field(
        default=None,
        description=(
            "Name of the environment variable holding the API key "
            "(e.g. 'OPENAI_API_KEY'). NEVER store the actual key in the config file."
        ),
    )
    request_timeout_s: float = Field(
        default=DEFAULT_REQUEST_TIMEOUT_S,
        gt=0,
        description="Blocking timeout per completion call, in seconds.",
    )

    @model_validator(mode="after")
    def _enforce_provider_requirements(self) -> "ModelEntry":
        """
        Each provider family has its own required fields. Validating here
        keeps invalid catalog entries from ever reaching the factory.
        """
        if self.provider == ProviderKind.OLLAMA and not self.base_url:
            raise ValueError("Ollama entries require 'base_url'.")

        if self.provider == ProviderKind.OPENAI_COMPAT:
            if not self.base_url:
                raise ValueError("OpenAI-compatible entries require 'base_url'.")
            if not self.api_key_env:
                raise ValueError("OpenAI-compatible entries require 'api_key_env'.")

        if self.provider == ProviderKind.ANTHROPIC and not self.api_key_env:
            raise ValueError("Anthropic entries require 'api_key_env'.")

        return self


class RoleName(StrEnum):
    """
    Roles that consume a model. Extend when new roles appear
    (e.g. ADVERSARIAL_ATTACKER in week 5).
    """

    PERSONA = "persona"
    JUDGE = "judge"


class RoleAssignments(BaseModel):
    """Maps each role to a catalog entry key."""

    persona: str = Field(description="Catalog key for the persona role.")
    judge: str = Field(description="Catalog key for the judge role.")

    def as_mapping(self) -> dict[RoleName, str]:
        """Return roles as an enum-keyed dict, convenient for iteration."""
        return {RoleName.PERSONA: self.persona, RoleName.JUDGE: self.judge}


class CivisConfig(BaseModel):
    """
    Complete CIVIS configuration, mirroring the TOML on disk.

    The invariant enforced below is what protects goal O3: the persona and
    judge roles must NEVER point to the same catalog entry — otherwise the
    judge would be evaluating output from its own model family.
    """

    models: dict[str, ModelEntry] = Field(
        default_factory=dict,
        description="Catalog of available models, keyed by name (e.g. 'qwen7b_local').",
    )
    roles: RoleAssignments

    @model_validator(mode="after")
    def _roles_point_to_existing_entries(self) -> "CivisConfig":
        for role_name, catalog_key in self.roles.as_mapping().items():
            if catalog_key not in self.models:
                raise ValueError(
                    f"Role '{role_name.value}' points to '{catalog_key}', "
                    f"which is not in the model catalog. "
                    f"Available: {sorted(self.models.keys())}"
                )
        return self

    @model_validator(mode="after")
    def _persona_and_judge_use_distinct_models(self) -> "CivisConfig":
        """
        Goal O3: the judge must run on a different model than the persona,
        to prevent self-evaluation. Distinct catalog KEYS is enough here — a
        stricter check (distinct provider or distinct model_id) is
        overreach: users may legitimately point two keys to the same model
        for experiments outside the scored run.
        """
        if self.roles.persona == self.roles.judge:
            raise ValueError(
                "Roles 'persona' and 'judge' must point to distinct catalog "
                "entries (goal O3: no self-evaluation)."
            )
        return self
