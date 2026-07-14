
# 🧞 JSON Genie — Text to Structured Data

Convert unstructured text (invoices, emails, job postings, or anything you
define) into clean, schema-validated JSON, powered by Pydantic v2 and native
LLM structured outputs.

## Architecture

json_genie/
├── app.py             # Streamlit UI (sidebar + main panel, split-screen results)
├── config.py          # Environment-driven settings (Settings dataclass)
├── models.py          # Pre-defined Pydantic schemas: Invoice, Email, JobPosting
├── schema_builder.py  # Runtime schema synthesis via pydantic.create_model
├── providers.py       # Anthropic / OpenAI structured-output adapters
├── extractor.py       # Orchestration: prompt -> LLM -> validate -> auto-repair
├── requirements.txt
├── .env.example
└── README.md


### Design principles applied

- **Single Responsibility**: each module owns exactly one concern — schemas,
  provider I/O, orchestration, or presentation.
- **Dependency Inversion**: `extractor.py` depends on the `StructuredLLMProvider`
  abstract interface, not on `anthropic` or `openai` directly. Swapping or
  adding a provider (e.g. Gemini) means implementing one class in
  `providers.py` — no changes to the extraction logic or the UI.
- **Fail-safe by design**: a `ValidationError` is treated as *data*, not an
  exception to crash on. `extractor.py` converts it into a corrective prompt
  and retries automatically (`MAX_REPAIR_ATTEMPTS`, default 2) before
  surfacing a clear, itemized failure report to the user.
- **Open/Closed for schemas**: adding a new pre-defined document type is a
  matter of adding one `BaseModel` and one registry entry in `models.py` — no
  changes to `app.py`, `extractor.py`, or `providers.py`.

## How structured output is guaranteed

- **Anthropic**: the target Pydantic model's JSON Schema (`schema.model_json_schema()`)
  is passed as a tool's `input_schema`, and `tool_choice` forces that tool to
  be called. The model's tool-call arguments are inherently shaped like the
  schema.
- **OpenAI**: uses native Structured Outputs
  (`response_format={"type": "json_schema", "strict": True, ...}`), which
  constrains token generation so the output is guaranteed to match the
  schema.

In both cases, **Pydantic's `model_validate()` is the final authority** —
it enforces business rules (`ge=0`, `gt=0`, required fields, etc.) that the
raw JSON Schema alone can't fully express, and any failure triggers the
auto-repair loop.

## Setup

```bash
cd json_genie
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and/or OPENAI_API_KEY
streamlit run app.py
```

## Using the app

1. **Sidebar → LLM Provider**: pick Anthropic or OpenAI (whichever key you set).
2. **Sidebar → Document Type**: choose Invoice, Email, Job Posting, or
   **Custom / Dynamic** to define your own schema on the fly (field name,
   type, description, required/optional — no code needed).
3. **Main panel**: paste your unstructured text and click **Extract Data**.
4. **Results**: the left column shows the validated JSON (with a download
   button); the right column shows the validation report, including how many
   auto-repair attempts were needed, or a detailed error list if extraction
   ultimately failed.

## Extending to a new pre-defined document type

Add a model and one registry line in `models.py`:

```python
class Receipt(BaseModel):
    merchant: str = Field(..., description="Store name")
    total: float = Field(..., ge=0)
    purchased_at: Optional[str] = None

DOCUMENT_TYPE_REGISTRY["Receipt"] = Receipt
```

It will immediately appear in the sidebar dropdown — no other file needs to change.

## Adding a new LLM provider

Implement `StructuredLLMProvider` in `providers.py` and register it in
`get_provider()`. `extractor.py` and `app.py` require no changes.

## Notes on production hardening

- API keys are read from environment variables only; never hard-code them.
- All I/O boundaries (`providers.py`) wrap SDK exceptions into a single
  `LLMProviderError`, so `extractor.py` never has to know about
  provider-specific exception types.
- `ExtractionResult` is a plain dataclass, safe to store in
  `st.session_state` and re-render across Streamlit reruns without
  re-calling the LLM.
- For a real production deployment, consider adding: request-level logging,
  rate limiting, a persistent audit trail of raw vs. validated payloads, and
  a background task queue for batch document processing.
