"""
providers.py
-------------
Thin adapter layer around LLM SDKs so the extraction engine stays
provider-agnostic (Dependency Inversion / SOLID). Each provider implements
`generate_json`, returning a raw (unvalidated) dict that *should* conform to
the given Pydantic schema, using the provider's native structured-output
mechanism:

  - Anthropic: forced tool-use, with the Pydantic JSON schema as the tool's
    `input_schema`. The model must call the tool, guaranteeing shaped JSON.
  - OpenAI: native Structured Outputs via
    `response_format={"type": "json_schema", "strict": True, ...}`, which
    guarantees the returned JSON matches the schema exactly.

Pydantic still performs the authoritative validation afterward in
`extractor.py` -- these providers only guarantee *shape*, not business-rule
correctness (e.g. `total_amount >= 0`).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Type

from pydantic import BaseModel

from config import Settings


class LLMProviderError(RuntimeError):
    """Raised when the underlying LLM call fails or returns unusable output."""


class StructuredLLMProvider(ABC):
    """Common interface every LLM backend must implement."""

    @abstractmethod
    def generate_json(self, text: str, schema: Type[BaseModel], system_prompt: str) -> dict[str, Any]:
        """Call the LLM and return a raw dict conforming (hopefully) to `schema`."""
        raise NotImplementedError


class AnthropicStructuredProvider(StructuredLLMProvider):
    """Structured output via Anthropic forced tool-use."""

    def __init__(self, settings: Settings) -> None:
        import anthropic  # local import: keeps the dependency optional at import time

        if not settings.anthropic_api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY is not set.")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

    def generate_json(self, text: str, schema: Type[BaseModel], system_prompt: str) -> dict[str, Any]:
        import anthropic

        tool_name = "extract_structured_data"
        json_schema = schema.model_json_schema()
        json_schema.pop("title", None)  # not needed inside input_schema

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_prompt,
                tools=[
                    {
                        "name": tool_name,
                        "description": "Extract structured data matching the required schema.",
                        "input_schema": json_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": text}],
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Anthropic API error: {exc}") from exc

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)

        raise LLMProviderError("Anthropic response did not contain the expected tool call.")


class OpenAIStructuredProvider(StructuredLLMProvider):
    """Structured output via OpenAI's native `json_schema` response format."""

    def __init__(self, settings: Settings) -> None:
        import openai  # local import: keeps the dependency optional at import time

        if not settings.openai_api_key:
            raise LLMProviderError("OPENAI_API_KEY is not set.")
        self._client = openai.OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

    def generate_json(self, text: str, schema: Type[BaseModel], system_prompt: str) -> dict[str, Any]:
        import openai

        json_schema = schema.model_json_schema()
        json_schema["additionalProperties"] = False

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": json_schema,
                        "strict": True,
                    },
                },
            )
        except openai.APIError as exc:
            raise LLMProviderError(f"OpenAI API error: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMProviderError("OpenAI response was empty.")
        return json.loads(content)


class GeminiStructuredProvider(StructuredLLMProvider):
    """
    Structured output via Google's Gemini API.

    Gemini's `response_schema` accepts an OpenAPI-flavored subset of JSON
    Schema -- notably it does NOT understand `$ref`/`$defs` (used by Pydantic
    for nested models) or keywords like `exclusiveMinimum`/`exclusiveMaximum`
    (produced by `gt=`/`lt=` constraints). Passing a raw Pydantic model class
    straight through fails validation inside the SDK, so we first convert the
    schema to a plain dict, inline every `$ref`, and strip/rewrite the
    keywords Gemini's `Schema` type doesn't recognize. Pydantic still
    performs the *real*, strict validation afterward in `extractor.py` --
    this sanitized schema only needs to be permissive enough to guide
    generation.
    """

    # Keys Gemini's Schema type does not accept at all.
    _UNSUPPORTED_KEYS = {"title", "default", "additionalProperties", "$defs"}

    def __init__(self, settings: Settings) -> None:
        from google import genai  # local import: keeps the dependency optional

        if not settings.gemini_api_key:
            raise LLMProviderError("GEMINI_API_KEY is not set.")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model
        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

    def generate_json(self, text: str, schema: Type[BaseModel], system_prompt: str) -> dict[str, Any]:
        from google.genai import errors, types

        gemini_schema = self._build_gemini_schema(schema)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=gemini_schema,
                    max_output_tokens=self._max_tokens,
                    temperature=self._temperature,
                ),
            )
        except errors.APIError as exc:
            raise LLMProviderError(f"Gemini API error: {exc}") from exc

        if not response.text:
            raise LLMProviderError("Gemini response was empty.")
        return json.loads(response.text)

    @classmethod
    def _build_gemini_schema(cls, schema: Type[BaseModel]) -> dict[str, Any]:
        """Convert a Pydantic model into a Gemini-compatible schema dict."""
        raw = schema.model_json_schema()
        defs = raw.get("$defs", {})
        resolved = cls._resolve_refs(raw, defs)
        return cls._strip_unsupported(resolved)

    @classmethod
    def _resolve_refs(cls, node: Any, defs: dict[str, Any]) -> Any:
        """Recursively inline every `$ref` since Gemini can't follow pointers."""
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].rsplit("/", 1)[-1]
                return cls._resolve_refs(defs.get(ref_name, {}), defs)
            return {k: cls._resolve_refs(v, defs) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [cls._resolve_refs(item, defs) for item in node]
        return node

    @classmethod
    def _strip_unsupported(cls, node: Any) -> Any:
        """
        Drop keys Gemini's Schema type rejects outright, and approximate
        `exclusiveMinimum`/`exclusiveMaximum` (unsupported) as
        `minimum`/`maximum` (supported). This is a slight loosening of the
        constraint (>= instead of >), which is fine because Pydantic
        re-validates the real rule afterward.
        """
        if isinstance(node, dict):
            cleaned: dict[str, Any] = {}
            for key, value in node.items():
                if key in cls._UNSUPPORTED_KEYS:
                    continue
                if key == "exclusiveMinimum":
                    cleaned["minimum"] = value
                    continue
                if key == "exclusiveMaximum":
                    cleaned["maximum"] = value
                    continue
                cleaned[key] = cls._strip_unsupported(value)
            return cleaned
        if isinstance(node, list):
            return [cls._strip_unsupported(item) for item in node]
        return node




def get_provider(settings: Settings, provider_name: str) -> StructuredLLMProvider:
    """Factory function returning the requested provider implementation."""
    if provider_name == "anthropic":
        return AnthropicStructuredProvider(settings)
    if provider_name == "openai":
        return OpenAIStructuredProvider(settings)
    if provider_name == "gemini":
        return GeminiStructuredProvider(settings)
    raise ValueError(f"Unknown provider: {provider_name}")
