"""
schema_builder.py
------------------
Utilities to build Pydantic models at RUNTIME from user-supplied field
definitions, powering the "Custom / Dynamic" document type in the UI.

This is the core of Objective #2: the same extraction engine adapts to any
new document type without a code change, by synthesizing a brand-new
`BaseModel` subclass via `pydantic.create_model`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field, create_model

# Mapping from a user-friendly type label (shown in the UI) to an actual
# Python/typing type used when constructing the dynamic model.
FIELD_TYPE_MAP: dict[str, Any] = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "date": date,
    "list[string]": List[str],
    "list[float]": List[float],
}


@dataclass
class FieldDefinition:
    """User-defined description of a single field in a dynamic schema."""

    name: str
    field_type: str  # must be a key in FIELD_TYPE_MAP
    description: str = ""
    required: bool = True

    def validate(self) -> None:
        """Basic sanity checks so bad UI input fails fast with a clear message."""
        if not self.name or not self.name.isidentifier():
            raise ValueError(
                f"Field name '{self.name}' is not a valid identifier. "
                "Use letters, numbers, and underscores only, and don't start with a digit."
            )
        if self.field_type not in FIELD_TYPE_MAP:
            raise ValueError(
                f"Unsupported field type '{self.field_type}'. "
                f"Choose one of: {', '.join(FIELD_TYPE_MAP)}"
            )


def build_dynamic_model(model_name: str, field_defs: List[FieldDefinition]) -> Type[BaseModel]:
    """
    Dynamically construct a Pydantic v2 model from a list of FieldDefinitions.

    Args:
        model_name: Name to give the generated class (used in error messages
            and, indirectly, in the JSON schema `title`).
        field_defs: The fields the user configured in the sidebar.

    Returns:
        A brand-new `BaseModel` subclass ready to be used for both prompting
        (via `.model_json_schema()`) and validation (via `.model_validate()`).

    Raises:
        ValueError: if no fields are supplied, a field definition is invalid,
            or duplicate field names are detected.
    """
    if not field_defs:
        raise ValueError("At least one field must be defined for a custom schema.")

    field_kwargs: dict[str, Any] = {}
    seen_names: set[str] = set()

    for fd in field_defs:
        fd.validate()
        if fd.name in seen_names:
            raise ValueError(f"Duplicate field name detected: '{fd.name}'")
        seen_names.add(fd.name)

        py_type = FIELD_TYPE_MAP[fd.field_type]
        annotation = py_type if fd.required else Optional[py_type]
        default = ... if fd.required else None

        field_kwargs[fd.name] = (annotation, Field(default=default, description=fd.description))

    safe_name = model_name.strip() if model_name and model_name.strip() else "CustomDocument"
    dynamic_model: Type[BaseModel] = create_model(safe_name, **field_kwargs)  # type: ignore[call-overload]
    return dynamic_model
