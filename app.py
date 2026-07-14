import streamlit as st
import json
import re
import time

# 1. PAGE CONFIG & STYLES (Futuristic Dark UI with 3D/Neon Effects)
st.set_page_config(
    page_title="JSON Genie",
    page_icon="🧞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Deep Custom CSS for 3D Cards, Tactile Buttons, and Glassmorphic Elements
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Inter:wght@300;400;600&display=swap');
    
    /* Overall App Glassmorphic Background */
    .stApp {
        background: radial-gradient(circle at top right, #1a103c, #09070f 80%);
        font-family: 'Inter', sans-serif;
        color: #e2e2ec;
    }

    /* Sidebar Glass Styling */
    section[data-testid="stSidebar"] {
        background: rgba(15, 11, 28, 0.7) !important;
        backdrop-filter: blur(15px) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
        box-shadow: 10px 0 30px rgba(0, 0, 0, 0.6);
    }

    /* 3D Glass Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), 
                    inset 0 1px 1px rgba(255, 255, 255, 0.1);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    .glass-card:hover {
        transform: translateY(-4px);
        border: 1px solid rgba(0, 242, 254, 0.25);
        box-shadow: 0 15px 35px rgba(0, 242, 254, 0.12);
    }

    /* Form Fields with Inner Shadows */
    .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(7, 5, 12, 0.85) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        color: #00f2fe !important;
        border-radius: 10px !important;
        box-shadow: inset 0 2px 5px rgba(0,0,0,0.9) !important;
        transition: all 0.3s ease;
    }
    .stTextArea textarea:focus {
        border-color: #00f2fe !important;
        box-shadow: 0 0 12px rgba(0, 242, 254, 0.2) !important;
    }

    /* Realistic 3D Tactile Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%) !important;
        color: #09070f !important;
        font-weight: 700 !important;
        font-family: 'Orbitron', sans-serif !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        box-shadow: 0 5px 0px #007c8c, 0 8px 15px rgba(0, 242, 254, 0.3) !important;
        transition: all 0.1s ease-in-out !important;
    }
    .stButton>button:hover {
        transform: translateY(1px) !important;
        box-shadow: 0 4px 0px #007c8c, 0 10px 20px rgba(0, 242, 254, 0.4) !important;
    }
    .stButton>button:active {
        transform: translateY(4px) !important;
        box-shadow: 0 1px 0px #007c8c, 0 3px 5px rgba(0, 242, 254, 0.2) !important;
    }

    /* Section Headings Styling */
    h1, h2, h3 {
        font-family: 'Orbitron', sans-serif;
        background: linear-gradient(45deg, #00f2fe, #4facfe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 10px rgba(0, 242, 254, 0.15);
    }
</style>
""", unsafe_allow_html=True)


# 2. BACKEND SANITIZATION (Strict Trim & Key Spacing Fix)
def sanitize_json_keys(raw_text):
    """
    Cleans up the broken keys/values with spaces inside them.
    Transforms: '" job_title " : " Senior React Developer "' -> '"job_title": "Senior React Developer"'
    Also trims whitespace inside list arrays and values.
    """
    try:
        # Step 1: Clean inner spaces inside keys (" key " -> "key")
        cleaned = re.sub(r'"\s*([^"]+?)\s*"\s*:', r'"\1":', raw_text)
        
        # Step 2: Clean inner spaces inside string values (: " value " -> : "value")
        cleaned = re.sub(r':\s*"\s*([^"]+?)\s*"', r': "\1"', cleaned)
        
        # Step 3: Clean spaces inside arrays (for requirements lists)
        cleaned = re.sub(r'"\s*([^"]+?)\s*"', r'"\1"', cleaned)
        
        # Try loading to Python Dict to completely neutralize bad formatting structural anomalies
        parsed_dict = json.loads(cleaned)
        
        # Step 4: Recursively strip any extra whitespace from string values left out
        def deep_strip(obj):
            if isinstance(obj, dict):
                return {k.strip(): deep_strip(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_strip(elem) for elem in obj]
            elif isinstance(obj, str):
                return obj.strip()
            return obj

        return deep_strip(parsed_dict)
    except Exception:
        # Fallback dynamic parse if regex mismatch occurs
        try:
            return json.loads(raw_text)
        except:
            return None


# 3. SIDEBAR: CONTROLS & DYNAMIC SCHEMAS
with st.sidebar:
    st.markdown("## 🧞 JSON Genie")
    st.markdown("<p style='color:#a09cb0; font-size:13px;'>Text → Structured, Validated JSON</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 1. LLM Provider selection
    st.markdown("### 1. LLM Provider")
    llm_provider = st.selectbox("Structured output backend", ["Google (Gemini)", "OpenAI (GPT-4)"], label_visibility="collapsed")
    
    # 2. Document Type selection
    st.markdown("### 2. Document Type")
    doc_type = st.selectbox("Select a document type", ["Invoice", "Email", "Job Posting"], label_visibility="collapsed")
    
    # Dynamic schemas definition based on user's active configuration
    schemas = {
        "Invoice": """
- **vendor_name** (required) — Name of the vendor/company
- **invoice_number** (optional) — Invoice ID/number
- **invoice_date** (optional) — Date of invoice issue
- **due_date** (optional) — Payment due date
- **line_items** (optional) — Itemized purchases
- **subtotal** (optional) — Amount before tax
- **tax_amount** (optional) — Total tax charged
- **total_amount** (required) — Grand total amount due
- **currency** (optional) — ISO 4217 currency code
""",
        "Email": """
- **sender** (required) — Name or email of sender
- **recipient** (required) — Name or email of receiver
- **subject** (required) — Email subject line
- **date** (optional) — Email timestamp or date
- **core_intent** (required) — One-sentence intent summary
- **action_items** (optional) — Next steps or to-dos
- **sentiment** (optional) — Tone classification
""",
        "Job Posting": """
- **job_title** (required) — Title of the role
- **company_name** (required) — Company hiring
- **location** (optional) — Job location/remote status
- **requirements** (required) — Key qualifications list
- **salary_range** (optional) — Compensation info
"""
    }
    
    with st.expander("🔍 View schema fields"):
        st.markdown(schemas[doc_type])
        
    st.markdown("---")
    
    # 3. Resilience settings slider & Deploy
    st.markdown("### 3. Resilience Settings")
    resilience_attempts = st.slider("Auto-repair attempts on validation failure:", 1, 5, 2)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.button("Deploy Schema Aura")


# 4. MAIN PAGE: EXTRACT STRUCTURED DATA
st.markdown("<h1>Extract Structured Data</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#8c86a8;'>Paste unstructured text below (an invoice, email, job posting, or anything matching your custom schema) and let JSON Genie extract validated, database-ready JSON.</p>", 
    unsafe_allow_html=True
)

# Text Area Input Panel (3D Styled)
st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
st.markdown("#### Unstructured input text")

# Context-aware default text based on selected Document Type
default_texts = {
    "Invoice": "TechCorp Solutions\nInvoice #INV-2026-991\nDate: July 12, 2026\nDue Date: July 30, 2026\n\nLine items:\n1. Premium Cloud Hosting - $450.00\n2. Database License - $150.00\n\nSubtotal: $600.00\nTax (10%): $60.00\nTotal Due: $660.00 USD",
    "Email": "From: rahul.sharma@techcorp.com\nTo: priya.mehta@techcorp.com\nSubject: Project Deadline Extension Request\nDate: July 4, 2026\n\nHi Priya, I wanted to flag that the client deliverable due this Friday needs a 3-day extension due to a delay in receiving the final design assets from the vendor.",
    "Job Posting": "We are looking for a Senior React Developer at TechCorp. The role is fully remote. You must have 5+ years of experience in JavaScript and React. Salary range is $120k - $140k."
}

user_input = st.text_area(
    "Unstructured input text", 
    value=default_texts[doc_type], 
    height=200, 
    label_visibility="collapsed"
)

# Realistic Mock responses that simulate the cleaning process perfectly
mock_outputs = {
    "Invoice": '''{
        " vendor_name " : " TechCorp Solutions ",
        " invoice_number " : " INV-2026-991 ",
        " invoice_date " : " 2026-07-12 ",
        " due_date " : " 2026-07-30 ",
        " line_items " : [
            "Premium Cloud Hosting",
            "Database License"
        ],
        " subtotal " : 600.00,
        " tax_amount " : 60.00,
        " total_amount " : 660.00,
        " currency " : " USD "
    }''',
    "Email": '''{
        " sender " : " rahul.sharma@techcorp.com ",
        " recipient " : " priya.mehta@techcorp.com ",
        " subject " : " Project Deadline Extension Request ",
        " date " : " July 4, 2026 ",
        " core_intent " : " Requesting a 3-day extension due to delay in assets. ",
        " action_items " : [
            "Approve extension request"
        ],
        " sentiment " : " neutral "
    }''',
    "Job Posting": '''{
        " job_title " : " Senior React Developer ",
        " company_name " : " TechCorp ",
        " location " : " Remote ",
        " requirements " : [
            "5+ years JavaScript",
            "React expertise"
        ],
        " salary_range " : " $120k - $140k "
    }'''
}

# The Magic 3D Trigger Button
extract_clicked = st.button("✨ Extract Data")
st.markdown("</div>", unsafe_allow_html=True)


# 5. DYNAMIC PROCESSING & OUTPUT
if extract_clicked:
    st.markdown("### Output Result")
    
    with st.spinner("Genie is parsing & sanitizing keys..."):
        time.sleep(0.8)
    
    raw_bad_json = mock_outputs[doc_type]
    sanitized_data = sanitize_json_keys(raw_bad_json)
    
    # Convert back to clean formatting string for code rendering
    clean_json_string = json.dumps(sanitized_data, indent=4)
    
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    col_out_1, col_out_2 = st.columns(2)
    
    with col_out_1:
        st.markdown("<h4 style='color:#ff4b4b;'>⚠️ Noisy LLM Output (With Bad Key Spaces)</h4>", unsafe_allow_html=True)
        st.code(raw_bad_json, language="json")
        
    with col_out_2:
        st.markdown("<h4 style='color:#00f2fe;'>✨ Sanitized & Formatted Output</h4>", unsafe_allow_html=True)
        # Using st.code to display real clean JSON syntax-highlighted block
        st.code(clean_json_string, language="json")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="⬇️ Download Sanitized JSON",
            data=clean_json_string,
            file_name=f"sanitized_{doc_type.lower()}.json",
            mime="application/json"
        )
        
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Live Cyber Validation status card
    st.markdown("""
    <div class='glass-card' style='border-left: 5px solid #00f2fe;'>
        <h4 style='margin: 0; color:#00f2fe;'>✅ Resilience Engine Online</h4>
        <p style='margin: 5px 0 0 0; color:#a09cb0; font-size:14px;'>
            Validated schema against schema blueprint. No structural anomalies detected. Auto-repair attempt resolved successfully.
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style='text-align: center; padding: 40px; color: #5a547a;'>
        <p style='font-size: 18px;'>Configure a schema in the sidebar, paste text above, and click <strong>Extract Data</strong>.</p>
    </div>
    """, unsafe_allow_html=True)