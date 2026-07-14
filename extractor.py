"""
extractor.py
-------------
Core extraction engine: turns unstructured text into a validated Pydantic
instance, with an auto-repair loop that feeds validation errors back to the
LLM when the first attempt doesn't validate.

This is the heart of Objective #3 (Resilience): rather than crashing on a
`ValidationError`, the engine treats it as feedback, builds a corrective
prompt describing exactly what was wrong, and retries up to
`Settings.max_repair_attempts` times before surfacing a clear failure report
to the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

from config import Settings
from json_utils import sanitize_json_output
from providers import LLMProviderError, StructuredLLMProvider, get_provider

BASE_SYSTEM_PROMPT = (
    "You are a meticulous data-extraction engine. Read the user's unstructured "
    "text and extract ONLY the information that is explicitly present or can be "
    "directly and safely inferred. Never invent facts, numbers, or names. If a "
    "field is genuinely not present in the text and the schema allows it to be "
    "absent, omit it rather than guessing. Always respond by calling the "
    "provided tool/function with your answer."
)


@dataclass
class ExtractionResult:
    """Outcome of an extraction attempt, safe to render directly in the UI."""

    success: bool
    data: Optional[BaseModel] = None
    raw_json: Optional[dict[str, Any]] = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    provider_used: str = ""


class StructuredExtractor:
    """
    Orchestrates: prompt -> LLM call -> Pydantic validation -> (optional) repair.

    The repair loop re-prompts the LLM with the exact validation errors it
    produced, which in practice resolves the majority of type mismatches and
    missing-required-field issues without any human intervention.
    """

    def __init__(self, settings: Settings, provider_name: str) -> None:
        self._settings = settings
        self._provider_name = provider_name
        self._provider: StructuredLLMProvider = get_provider(settings, provider_name)

    def extract(self, text: str, schema: Type[BaseModel]) -> ExtractionResult:
        """Run the full extract -> validate -> repair pipeline for `text` against `schema`."""
        if not text or not text.strip():
            return ExtractionResult(
                success=False,
                errors=["Input text is empty. Please provide some text to extract from."],
                provider_used=self._provider_name,
            )

        max_attempts = max(1, self._settings.max_repair_attempts + 1)
        last_errors: list[str] = []
        raw: Optional[dict[str, Any]] = None

        for attempt in range(1, max_attempts + 1):
            system_prompt = self._build_system_prompt(last_errors)
            try:
                raw = self._provider.generate_json(text, schema, system_prompt)
            except LLMProviderError as exc:
                return ExtractionResult(
                    success=False,
                    errors=[f"LLM call failed: {exc}"],
                    attempts=attempt,
                    provider_used=self._provider_name,
                )

            # Defensive cleanup: strip stray whitespace from every key and
            # string value BEFORE validation. Without this, a padded key like
            # `" sender "` from the raw model output would silently fail
            # Pydantic's field matching (and get treated as a missing
            # required field) instead of being recognized as `sender`.
            raw = sanitize_json_output(raw)

            try:
                validated = schema.model_validate(raw)
                return ExtractionResult(
                    success=True,
                    data=validated,
                    raw_json=raw,
                    attempts=attempt,
                    provider_used=self._provider_name,
                )
            except ValidationError as exc:
                last_errors = self._format_validation_errors(exc)
                continue

        # All attempts exhausted: surface the last raw payload and errors so the
        # user can see exactly what the LLM produced and why it was rejected.
        return ExtractionResult(
            success=False,
            raw_json=raw,
            errors=last_errors or ["Extraction failed for an unknown reason."],
            attempts=max_attempts,
            provider_used=self._provider_name,
        )

    @staticmethod
    def _format_validation_errors(exc: ValidationError) -> list[str]:
        """Turn Pydantic's ValidationError into short, LLM- and human-readable strings."""
        messages = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            messages.append(f"Field '{loc}': {err['msg']}")
        return messages

    @staticmethod
    def _build_system_prompt(previous_errors: list[str]) -> str:
        """Augment the base prompt with repair instructions if a prior attempt failed."""
        if not previous_errors:
            return BASE_SYSTEM_PROMPT
        error_block = "\n".join(f"- {e}" for e in previous_errors)
        return (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Your previous attempt to call the tool failed validation with these "
            f"errors:\n{error_block}\n\n"
            "Correct these specific issues and call the tool again with fixed data."
        )
