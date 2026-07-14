"""
models.py
----------
Pydantic v2 schema definitions for all pre-defined document types.

Design notes:
- Fields that are almost always present and load-bearing for downstream DB
  ingestion (e.g. `vendor_name`, `total_amount`) are required.
- Fields that are frequently absent in real-world text (e.g. `due_date`,
  `salary_range`) are Optional, so the model doesn't force the LLM to
  hallucinate a value just to satisfy validation.
- `field_validator` is used on `LineItem.total` as a small "auto-repair"
  example: if the LLM forgets to compute the line total, Pydantic derives it
  during validation instead of failing outright.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    """A single line item on an invoice."""

    description: str = Field(..., description="Description of the product/service")
    quantity: float = Field(..., gt=0, description="Quantity purchased")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    total: Optional[float] = Field(
        default=None, description="Line total (quantity * unit_price), if stated"
    )

    @field_validator("total")
    @classmethod
    def fill_total_if_missing(cls, v: Optional[float], info) -> Optional[float]:
        """Auto-repair: compute the line total if the LLM omitted it."""
        if v is None:
            data = info.data
            qty = data.get("quantity")
            price = data.get("unit_price")
            if qty is not None and price is not None:
                return round(qty * price, 2)
        return v


class Invoice(BaseModel):
    """Structured representation of an invoice."""

    vendor_name: str = Field(..., description="Name of the vendor/company issuing the invoice")
    invoice_number: Optional[str] = Field(default=None, description="Invoice ID/number")
    invoice_date: Optional[str] = Field(default=None, description="Date of invoice issue (ISO 8601 preferred)")
    due_date: Optional[str] = Field(default=None, description="Payment due date, if stated")
    line_items: List[LineItem] = Field(default_factory=list, description="Itemized purchases")
    subtotal: Optional[float] = Field(default=None, ge=0, description="Amount before tax")
    tax_amount: Optional[float] = Field(default=None, ge=0, description="Total tax charged")
    total_amount: float = Field(..., ge=0, description="Grand total amount due")
    currency: Optional[str] = Field(default="USD", description="ISO 4217 currency code")


class Email(BaseModel):
    """Structured representation of an email."""

    sender: str = Field(..., description="Email address or name of the sender")
    recipient: str = Field(..., description="Email address or name of the recipient")
    subject: str = Field(..., description="Email subject line")
    date: Optional[str] = Field(default=None, description="Date the email was sent")
    core_intent: str = Field(..., description="One-sentence summary of the email's purpose")
    action_items: List[str] = Field(default_factory=list, description="Explicit action items / to-dos")
    sentiment: Optional[str] = Field(default=None, description="Overall tone: positive/neutral/negative")


class JobPosting(BaseModel):
    """Structured representation of a job posting."""

    job_title: str = Field(..., description="Title of the position")
    company: str = Field(..., description="Hiring company name")
    location: str = Field(..., description="Job location (city, remote, or hybrid)")
    required_skills: List[str] = Field(default_factory=list, description="Required technical/soft skills")
    salary_range: Optional[str] = Field(default=None, description="Stated salary range, if any")
    experience_required: Optional[str] = Field(default=None, description="Years/level of experience required")
    employment_type: Optional[str] = Field(default=None, description="Full-time, Part-time, or Contract")


# Registry mapping a human-friendly document type name to its Pydantic model.
# The UI reads this to populate the sidebar dropdown, and the extractor reads
# it to fetch the target schema for validation.
DOCUMENT_TYPE_REGISTRY: dict[str, type[BaseModel]] = {
    "Invoice": Invoice,
    "Email": Email,
    "Job Posting": JobPosting,
}
