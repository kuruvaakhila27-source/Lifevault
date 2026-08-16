import streamlit as st
import fitz
import re
import sqlite3
import requests
from datetime import datetime, date

# =====================================================
# PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="LifeVault",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# BASIC SECURITY / LIMITS
# =====================================================

MAX_FILE_SIZE_MB = 10
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

# =====================================================
# DATABASE
# =====================================================

conn = sqlite3.connect(
    "lifevault.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    document_type TEXT,
    invoice_number TEXT,
    product TEXT,
    purchase_date TEXT,
    amount TEXT,
    warranty TEXT,
    warranty_expiry TEXT,
    seller TEXT
)
""")

conn.commit()

# Add category column if database is older
cursor.execute("PRAGMA table_info(documents)")
existing_columns = [row[1] for row in cursor.fetchall()]

if "category" not in existing_columns:
    cursor.execute(
        "ALTER TABLE documents ADD COLUMN category TEXT DEFAULT 'Other'"
    )

conn.commit()

# =====================================================
# HELPERS
# =====================================================

def clean_text(value):
    """Basic text cleanup."""
    if not value:
        return "Not found"

    value = str(value).strip()

    # Avoid displaying extremely long values
    if len(value) > 500:
        value = value[:500] + "..."

    return value


def calculate_days_left(expiry_text):
    """
    Convert common date formats and calculate remaining days.
    Returns None if the date cannot be understood.
    """

    if not expiry_text or expiry_text == "Not found":
        return None

    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            expiry_date = datetime.strptime(
                expiry_text.strip(),
                fmt
            ).date()

            return (expiry_date - date.today()).days

        except ValueError:
            continue

    return None


def expiry_status(expiry_text):
    """Return status, days remaining and display message."""

    days = calculate_days_left(expiry_text)

    if days is None:
        return "⚪ Unknown", None

    if days < 0:
        return "🔴 Expired", days

    if days <= 30:
        return "🔴 Expires Soon", days

    if days <= 90:
        return "🟡 Upcoming", days

    return "🟢 Active", days


def ask_ollama(prompt):
    """Send a prompt to the local Ollama model."""

    try:

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        if response.status_code == 200:

            data = response.json()

            return data.get(
                "response",
                "AI could not generate a response."
            )

        return f"❌ Ollama error: {response.status_code}"

    except requests.exceptions.ConnectionError:

        return (
            "❌ Ollama is not running.\n\n"
            "Please start Ollama and try again."
        )

    except requests.exceptions.Timeout:

        return (
            "⏳ AI took too long to respond. "
            "Please try again."
        )

    except Exception as e:

        return f"❌ AI error: {str(e)}"


def detect_category(text):
    """Automatically classify a document."""

    text_lower = text.lower()

    if any(
        word in text_lower
        for word in [
            "invoice",
            "receipt",
            "purchase amount",
            "invoice number"
        ]
    ):
        return "Shopping / Invoice"

    if any(
        word in text_lower
        for word in [
            "warranty",
            "warranty period",
            "warranty expiry"
        ]
    ):
        return "Warranty"

    if any(
        word in text_lower
        for word in [
            "rental agreement",
            "lease agreement",
            "tenant",
            "landlord"
        ]
    ):
        return "Agreement"

    if any(
        word in text_lower
        for word in [
            "insurance",
            "policy number",
            "premium"
        ]
    ):
        return "Insurance"

    if any(
        word in text_lower
        for word in [
            "vehicle",
            "registration",
            "rc number",
            "car"
        ]
    ):
        return "Vehicle"

    if any(
        word in text_lower
        for word in [
            "education",
            "college",
            "university",
            "student"
        ]
    ):
        return "Education"

    return "Other"


def format_document_for_ai(documents):
    """Create safe context for Ask LifeVault."""

    context = ""

    for doc in documents:

        context += f"""
DOCUMENT:
Filename: {doc[1]}
Type: {doc[2]}
Invoice: {doc[3]}
Product: {doc[4]}
Purchase Date: {doc[5]}
Amount: {doc[6]}
Warranty: {doc[7]}
Warranty Expiry: {doc[8]}
Seller: {doc[9]}
Category: {doc[10] if len(doc) > 10 else "Other"}

-------------------------
"""

    # Limit context size
    if len(context) > 12000:
        context = context[:12000]

    return context


# =====================================================
# CUSTOM CSS
# =====================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 700;
        margin-bottom: 0;
    }

    .subtitle {
        color: #777;
        font-size: 18px;
    }

    .small-note {
        color: #888;
        font-size: 13px;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# =====================================================
# HEADER
# =====================================================

st.markdown(
    '<div class="main-title">🔐 LifeVault</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Your Personal Digital Vault</div>',
    unsafe_allow_html=True
)

st.write(
    "Store, organize and understand your important documents "
    "in one secure place."
)

st.divider()

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.title("🔐 LifeVault")

st.sidebar.caption(
    "Your documents. Your information. One vault."
)

page = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Dashboard",
        "📤 Upload Document",
        "📚 My Documents",
        "🔍 Search Vault",
        "🤖 Ask LifeVault"
    ]
)

st.sidebar.divider()

st.sidebar.caption(
    "🔒 Basic local privacy enabled"
)

# =====================================================
# DASHBOARD
# =====================================================

if page == "🏠 Dashboard":

    st.header("📊 Vault Dashboard")

    cursor.execute(
        "SELECT * FROM documents ORDER BY id DESC"
    )

    documents = cursor.fetchall()

    total_documents = len(documents)

    total_receipts = sum(
        1
        for doc in documents
        if "Invoice" in str(doc[2])
        or "Receipt" in str(doc[2])
    )

    total_warranties = sum(
        1
        for doc in documents
        if doc[8] and doc[8] != "Not found"
    )

    expired_count = 0
    upcoming_count = 0

    for doc in documents:

        status, days = expiry_status(doc[8])

        if days is not None:

            if days < 0:
                expired_count += 1

            elif days <= 90:
                upcoming_count += 1

    # -------------------------------------------------
    # METRICS
    # -------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📄 Documents",
            total_documents
        )

    with col2:
        st.metric(
            "🧾 Invoices",
            total_receipts
        )

    with col3:
        st.metric(
            "🛡️ Warranties",
            total_warranties
        )

    with col4:
        st.metric(
            "⏰ Expiring Soon",
            upcoming_count
        )

    st.divider()

    # -------------------------------------------------
    # ALERTS
    # -------------------------------------------------

    st.header("🔔 Smart Alerts")

    if expired_count > 0:

        st.error(
            f"🔴 You have {expired_count} expired document(s) or warranty(ies)."
        )

    if upcoming_count > 0:

        st.warning(
            f"🟡 {upcoming_count} document(s) need your attention soon."
        )

    if expired_count == 0 and upcoming_count == 0:

        st.success(
            "🟢 No urgent expiry alerts right now."
        )

    # -------------------------------------------------
    # UPCOMING EXPIRIES
    # -------------------------------------------------

    st.divider()

    st.header("⏰ Upcoming Expiries")

    expiry_documents = []

    for doc in documents:

        status, days = expiry_status(doc[8])

        if days is not None:

            expiry_documents.append(
                (days, doc, status)
            )

    expiry_documents.sort(
        key=lambda x: x[0]
    )

    if expiry_documents:

        for days, doc, status in expiry_documents[:5]:

            if days < 0:

                message = (
                    f"Expired {abs(days)} day(s) ago"
                )

            else:

                message = (
                    f"{days} day(s) remaining"
                )

            st.info(
                f"**{doc[4]}**  \n"
                f"📅 Expiry: **{doc[8]}**  \n"
                f"{status} • {message}"
            )

    else:

        st.info(
            "No expiry dates available yet."
        )

    # -------------------------------------------------
    # CATEGORY SUMMARY
    # -------------------------------------------------

    st.divider()

    st.header("🗂️ Document Categories")

    categories = {}

    for doc in documents:

        category = (
            doc[10]
            if len(doc) > 10 and doc[10]
            else "Other"
        )

        categories[category] = (
            categories.get(category, 0) + 1
        )

    if categories:

        cols = st.columns(
            min(len(categories), 4)
        )

        for index, (category, count) in enumerate(
            categories.items()
        ):

            with cols[index % len(cols)]:

                st.metric(
                    category,
                    count
                )

    else:

        st.info(
            "Upload documents to see categories."
        )

# =====================================================
# UPLOAD DOCUMENT
# =====================================================

elif page == "📤 Upload Document":

    st.header("📤 Upload a Document")

    st.caption(
        "Maximum file size: 10 MB"
    )

    uploaded_file = st.file_uploader(
        "Upload a PDF",
        type=["pdf"]
    )

    if uploaded_file:

        # -------------------------------------------------
        # FILE SECURITY CHECK
        # -------------------------------------------------

        if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:

            st.error(
                "❌ File is too large. "
                "Please upload a PDF smaller than 10 MB."
            )

            st.stop()

        if not uploaded_file.name.lower().endswith(".pdf"):

            st.error(
                "❌ Only PDF files are allowed."
            )

            st.stop()

        st.success(
            f"Uploaded: {uploaded_file.name}"
        )

        pdf_data = uploaded_file.read()

        try:

            document = fitz.open(
                stream=pdf_data,
                filetype="pdf"
            )

            extracted_text = ""

            for pdf_page in document:

                extracted_text += (
                    pdf_page.get_text()
                )

            document.close()

        except Exception:

            st.error(
                "❌ Could not read this PDF."
            )

            st.stop()

        if not extracted_text.strip():

            st.warning(
                "⚠️ No readable text was found in this PDF."
            )

            st.info(
                "Scanned/image-only PDFs need OCR support."
            )

            st.stop()

        # -------------------------------------------------
        # TEXT
        # -------------------------------------------------

        st.subheader("📄 Extracted Document Text")

        st.text_area(
            "Document Content",
            extracted_text,
            height=300
        )

        # -------------------------------------------------
        # INFORMATION EXTRACTION
        # -------------------------------------------------

        invoice_match = re.search(
            r"Invoice Number:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        invoice_number = clean_text(
            invoice_match.group(1)
            if invoice_match
            else "Not found"
        )

        product_match = re.search(
            r"Product:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        product = clean_text(
            product_match.group(1)
            if product_match
            else "Not found"
        )

        date_match = re.search(
            r"Purchase Date:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        purchase_date = clean_text(
            date_match.group(1)
            if date_match
            else "Not found"
        )

        amount_match = re.search(
            r"Purchase Amount:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        amount = clean_text(
            amount_match.group(1)
            if amount_match
            else "Not found"
        )

        warranty_match = re.search(
            r"Warranty Period:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        warranty = clean_text(
            warranty_match.group(1)
            if warranty_match
            else "Not found"
        )

        expiry_match = re.search(
            r"Warranty Expiry:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        warranty_expiry = clean_text(
            expiry_match.group(1)
            if expiry_match
            else "Not found"
        )

        seller_match = re.search(
            r"Seller:\s*(.+)",
            extracted_text,
            re.IGNORECASE
        )

        seller = clean_text(
            seller_match.group(1)
            if seller_match
            else "Not found"
        )

        # -------------------------------------------------
        # TYPE
        # -------------------------------------------------

        if "invoice" in extracted_text.lower():

            document_type = "Invoice / Receipt"

        elif "agreement" in extracted_text.lower():

            document_type = "Agreement"

        elif "warranty" in extracted_text.lower():

            document_type = "Warranty Document"

        else:

            document_type = "Other Document"

        # -------------------------------------------------
        # CATEGORY
        # -------------------------------------------------

        category = detect_category(
            extracted_text
        )

        # -------------------------------------------------
        # DOCUMENT INFORMATION
        # -------------------------------------------------

        st.divider()

        st.header("🧠 Document Information")

        col1, col2 = st.columns(2)

        with col1:

            st.info(
                f"**📄 Type**\n\n{document_type}"
            )

            st.info(
                f"**🗂️ Category**\n\n{category}"
            )

            st.info(
                f"**📦 Product**\n\n{product}"
            )

            st.info(
                f"**📅 Purchase Date**\n\n{purchase_date}"
            )

            st.info(
                f"**🔢 Invoice**\n\n{invoice_number}"
            )

        with col2:

            st.info(
                f"**💰 Amount**\n\n{amount}"
            )

            st.info(
                f"**🛡️ Warranty**\n\n{warranty}"
            )

            st.info(
                f"**⏰ Warranty Expiry**\n\n{warranty_expiry}"
            )

            st.info(
                f"**🏪 Seller**\n\n{seller}"
            )

        # -------------------------------------------------
        # SMART EXPIRY
        # -------------------------------------------------

        st.divider()

        st.header("⏰ Smart Expiry Tracking")

        status, days = expiry_status(
            warranty_expiry
        )

        if days is None:

            st.info(
                "No readable expiry date was found."
            )

        elif days < 0:

            st.error(
                f"🔴 Warranty expired "
                f"{abs(days)} day(s) ago."
            )

        elif days <= 30:

            st.error(
                f"🔴 Warranty expires in "
                f"**{days} day(s)**."
            )

        elif days <= 90:

            st.warning(
                f"🟡 Warranty expires in "
                f"**{days} day(s)**."
            )

        else:

            st.success(
                f"🟢 Warranty is active. "
                f"**{days} day(s)** remaining."
            )

        # -------------------------------------------------
        # AI
        # -------------------------------------------------

        st.divider()

        st.header("🤖 AI Document Understanding")

        if st.button(
            "✨ Analyze Document with AI",
            type="primary"
        ):

            with st.spinner(
                "🧠 LifeVault AI is analyzing..."
            ):

                prompt = f"""
You are LifeVault, a personal document assistant.

Analyze ONLY the following document.

DOCUMENT:
{extracted_text[:12000]}

Give the answer in these sections:

📌 Summary
🔑 Important Information
⚠️ Important Dates
💡 Recommended Action

Rules:
- Do not invent facts.
- Use only information present in the document.
- Keep the response concise.
- Use simple English.
"""

                ai_result = ask_ollama(
                    prompt
                )

            st.success(
                "✅ AI analysis completed!"
            )

            st.markdown(
                ai_result
            )

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------

        st.divider()

        if st.button(
            "💾 Save to LifeVault",
            type="secondary"
        ):

            cursor.execute(
                """
                INSERT INTO documents
                (
                    filename,
                    document_type,
                    invoice_number,
                    product,
                    purchase_date,
                    amount,
                    warranty,
                    warranty_expiry,
                    seller,
                    category
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uploaded_file.name,
                    document_type,
                    invoice_number,
                    product,
                    purchase_date,
                    amount,
                    warranty,
                    warranty_expiry,
                    seller,
                    category
                )
            )

            conn.commit()

            st.success(
                "✅ Document saved successfully!"
            )

# =====================================================
# MY DOCUMENTS
# =====================================================

elif page == "📚 My Documents":

    st.header("📚 My Documents")

    cursor.execute(
        "SELECT * FROM documents ORDER BY id DESC"
    )

    documents = cursor.fetchall()

    if not documents:

        st.info(
            "📭 No documents saved yet."
        )

    else:

        for doc in documents:

            (
                doc_id,
                filename,
                document_type,
                invoice_number,
                product,
                purchase_date,
                amount,
                warranty,
                warranty_expiry,
                seller,
                category
            ) = doc

            status, days = expiry_status(
                warranty_expiry
            )

            with st.expander(
                f"📄 {filename}"
            ):

                col1, col2 = st.columns(2)

                with col1:

                    st.write(
                        f"**Category:** {category}"
                    )

                    st.write(
                        f"**Type:** {document_type}"
                    )

                    st.write(
                        f"**Product:** {product}"
                    )

                    st.write(
                        f"**Invoice:** {invoice_number}"
                    )

                    st.write(
                        f"**Seller:** {seller}"
                    )

                with col2:

                    st.write(
                        f"**Purchase Date:** {purchase_date}"
                    )

                    st.write(
                        f"**Amount:** {amount}"
                    )

                    st.write(
                        f"**Warranty:** {warranty}"
                    )

                    st.write(
                        f"**Warranty Expiry:** {warranty_expiry}"
                    )

                    st.write(
                        f"**Status:** {status}"
                    )

                # -------------------------------------------------
                # MANAGEMENT
                # -------------------------------------------------

                st.divider()

                confirm_delete = st.checkbox(
                    "⚠️ Select to enable delete",
                    key=f"confirm_{doc_id}"
                )

                if confirm_delete:

                    if st.button(
                        "🗑️ Delete Document",
                        key=f"delete_{doc_id}"
                    ):

                        cursor.execute(
                            "DELETE FROM documents WHERE id = ?",
                            (doc_id,)
                        )

                        conn.commit()

                        st.success(
                            "✅ Document deleted."
                        )

                        st.rerun()

# =====================================================
# SEARCH
# =====================================================

elif page == "🔍 Search Vault":

    st.header("🔍 Search Your Vault")

    query = st.text_input(
        "Search",
        placeholder="Example: washing machine"
    )

    category_filter = st.selectbox(
        "🗂️ Filter by category",
        [
            "All",
            "Shopping / Invoice",
            "Warranty",
            "Agreement",
            "Insurance",
            "Vehicle",
            "Education",
            "Other"
        ]
    )

    if query or category_filter != "All":

        cursor.execute(
            "SELECT * FROM documents ORDER BY id DESC"
        )

        all_documents = cursor.fetchall()

        results = []

        for doc in all_documents:

            searchable_text = " ".join(
                str(value)
                for value in doc
            ).lower()

            matches_query = (
                not query
                or query.lower() in searchable_text
            )

            matches_category = (
                category_filter == "All"
                or doc[10] == category_filter
            )

            if matches_query and matches_category:

                results.append(doc)

        if results:

            st.success(
                f"Found {len(results)} result(s)."
            )

            for doc in results:

                with st.expander(
                    f"📄 {doc[1]}"
                ):

                    st.write(
                        f"**Category:** {doc[10]}"
                    )

                    st.write(
                        f"**Product:** {doc[4]}"
                    )

                    st.write(
                        f"**Invoice:** {doc[3]}"
                    )

                    st.write(
                        f"**Amount:** {doc[6]}"
                    )

                    st.write(
                        f"**Warranty:** {doc[7]}"
                    )

                    st.write(
                        f"**Warranty Expiry:** {doc[8]}"
                    )

                    st.write(
                        f"**Seller:** {doc[9]}"
                    )

        else:

            st.warning(
                "❌ No matching documents found."
            )

# =====================================================
# ASK LIFEVAULT
# =====================================================

elif page == "🤖 Ask LifeVault":

    st.header("🤖 Ask LifeVault")

    st.write(
        "Ask questions about the information stored "
        "in your document vault."
    )

    question = st.text_input(
        "💬 What would you like to know?",
        placeholder=(
            "Example: When does my washing machine "
            "warranty expire?"
        )
    )

    if question:

        cursor.execute(
            "SELECT * FROM documents ORDER BY id DESC"
        )

        documents = cursor.fetchall()

        if not documents:

            st.warning(
                "📭 Your vault is empty. "
                "Upload a document first."
            )

        else:

            vault_information = format_document_for_ai(
                documents
            )

            with st.spinner(
                "🧠 LifeVault AI is thinking..."
            ):

                prompt = f"""
You are LifeVault, a private document assistant.

Use ONLY the following vault information.

VAULT:
{vault_information}

USER QUESTION:
{question}

Instructions:
- Answer directly.
- Do not invent information.
- If the answer is unavailable, say:
  "I couldn't find that information in your vault."
- Mention the relevant document when useful.
- Keep the answer concise and easy to understand.
"""

                answer = ask_ollama(
                    prompt
                )

            st.success(
                "🤖 LifeVault AI"
            )

            st.markdown(
                answer
            )

# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "🔐 LifeVault • Your important information, "
    "organized intelligently."
)