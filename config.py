"""
config.py
----------
Centralized configuration for JSON Genie.
Loads environment variables and exposes a single, typed, immutable Settings
object used across the application. Keeping configuration in one place makes
the app easy to deploy across environments (local, Docker, Streamlit Cloud).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class LLMProviderName(str, Enum):
    """Supported LLM backends."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


@dataclass(frozen=True)
class Settings:
    """Immutable application settings, populated once at startup."""

    anthropic_api_key: str | None
    openai_api_key: str | None
    gemini_api_key: str | None
    default_provider: LLMProviderName
    anthropic_model: str
    openai_model: str
    gemini_model: str
    max_repair_attempts: int
    max_tokens: int
    temperature: float


def get_settings() -> Settings:
    """Build a Settings instance from environment variables, with safe defaults."""
    provider_raw = os.getenv("DEFAULT_LLM_PROVIDER", "anthropic").lower()
    try:
        default_provider = LLMProviderName(provider_raw)
    except ValueError:
        default_provider = LLMProviderName.ANTHROPIC

    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        default_provider=default_provider,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        max_repair_attempts=int(os.getenv("MAX_REPAIR_ATTEMPTS", "2")),
        max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
        temperature=float(os.getenv("TEMPERATURE", "0.0")),
    )
