import streamlit as st
from anthropic import Anthropic
import io
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.enums import TA_LEFT

# ── Constants ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"

PRIMER_SYSTEM = """You are a senior equity research analyst with 20+ years covering businesses across every sector. \
When given a company description you produce a concise but substantive briefing primer for a junior analyst \
who needs to get smart fast before building a financial model.

Produce the primer in exactly this structure — use these exact markdown headers:

## 1. Revenue Mechanics
How the company actually makes money. Pricing model, revenue streams, what moves the top line. Be specific.

## 2. Cost Structure & Margins
Key cost drivers. Is this a fixed-cost or variable-cost model? Gross margin profile, EBITDA margin range, \
operating leverage dynamics.

## 3. Key KPIs
List 3–5 KPIs that are specific to this business. For each, explain briefly WHY it matters — not just what it is.

## 4. Biggest Business Risks
The two or three risks that could actually break the investment thesis. Be honest; skip boilerplate risks that \
apply to every company.

## 5. What to Watch in the Financial Model
Specific line items, ratios, and trends an analyst should focus on when building or stress-testing the model. \
Name them explicitly.

Write in plain, direct language. No jargon without explanation. \
This is a colleague briefing — not a slide deck."""

CHAT_SYSTEM_TEMPLATE = """You are a senior equity research analyst. You have just produced the following \
business model primer for a company, and the analyst is now asking follow-up questions.

--- PRIMER ---
{primer}
--- END PRIMER ---

Answer follow-up questions like a knowledgeable colleague: direct, specific, no fluff. \
Reference the primer context where relevant. Keep answers concise but complete."""

# ── PDF helper ────────────────────────────────────────────────────────────────

ACCENT = colors.HexColor("#1450A0")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
DARK_TEXT = colors.HexColor("#1A1A1A")
MID_TEXT = colors.HexColor("#444444")


def _build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=ACCENT,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica",
            fontSize=10,
            textColor=MID_TEXT,
            spaceAfter=12,
            alignment=TA_LEFT,
        ),
        "company_box": ParagraphStyle(
            "company_box",
            fontName="Helvetica",
            fontSize=10,
            textColor=MID_TEXT,
            leftIndent=8,
            rightIndent=8,
            spaceBefore=4,
            spaceAfter=4,
            leading=14,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=ACCENT,
            spaceBefore=14,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=DARK_TEXT,
            leading=15,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=10,
            textColor=DARK_TEXT,
            leading=15,
            leftIndent=14,
            spaceAfter=3,
        ),
    }
    return styles


def _md_to_rl(text: str) -> str:
    """Convert basic markdown bold/italic to ReportLab XML."""
    # Bold: **text** → <b>text</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic: *text* → <i>text</i>
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


def build_pdf(company_description: str, primer_text: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    S = _build_styles()
    story = []

    story.append(Paragraph("Business Model Cheat Sheet", S["title"]))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
    story.append(Spacer(1, 6))
    story.append(Paragraph(company_description, S["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 8))

    for line in primer_text.split("\n"):
        line = line.rstrip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        if line.startswith("## "):
            story.append(Paragraph(_md_to_rl(line[3:]), S["section_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=4))
        elif line.startswith("### "):
            story.append(Paragraph(_md_to_rl(line[4:]), S["section_heading"]))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph("•  " + _md_to_rl(line[2:]), S["bullet"]))
        else:
            story.append(Paragraph(_md_to_rl(line), S["body"]))

    doc.build(story)
    return buf.getvalue()


# ── Streamlit app ─────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "primer": None,
        "company_description": "",
        "messages": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def stream_primer(client: Anthropic, description: str) -> str:
    placeholder = st.empty()
    collected: list[str] = []
    with client.messages.stream(
        model=MODEL,
        max_tokens=1800,
        system=PRIMER_SYSTEM,
        messages=[{"role": "user", "content": description}],
    ) as stream:
        for chunk in stream.text_stream:
            collected.append(chunk)
            placeholder.markdown("".join(collected) + "▌")
    full_text = "".join(collected)
    placeholder.markdown(full_text)
    return full_text


def stream_chat(client: Anthropic, user_msg: str) -> str:
    system = CHAT_SYSTEM_TEMPLATE.format(primer=st.session_state.primer)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    history.append({"role": "user", "content": user_msg})

    placeholder = st.empty()
    collected: list[str] = []
    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=history,
    ) as stream:
        for chunk in stream.text_stream:
            collected.append(chunk)
            placeholder.markdown("".join(collected) + "▌")
    full_text = "".join(collected)
    placeholder.markdown(full_text)
    return full_text


def main():
    st.set_page_config(
        page_title="Business Model Tutor",
        page_icon="📊",
        layout="centered",
    )

    init_state()
    client = Anthropic()

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("Business Model Tutor")
    st.caption(
        "Paste a 2–3 sentence company description and get an analyst-grade primer instantly. "
        "Then ask follow-up questions — the agent knows this business cold."
    )
    st.divider()

    # ── Input section ─────────────────────────────────────────────────────────
    description = st.text_area(
        "Company description",
        placeholder=(
            "e.g. Snowflake is a cloud data platform that sells compute and storage "
            "to enterprises on a consumption-based pricing model. Customers query data "
            "warehouses hosted on AWS, Azure, and GCP and pay per credit consumed."
        ),
        height=110,
        label_visibility="collapsed",
    )

    col_btn, col_export = st.columns([1, 1])
    with col_btn:
        generate = st.button(
            "Generate Primer",
            type="primary",
            use_container_width=True,
            disabled=not description.strip(),
        )
    with col_export:
        if st.session_state.primer:
            pdf_bytes = build_pdf(
                st.session_state.company_description,
                st.session_state.primer,
            )
            st.download_button(
                "Export Cheat Sheet (PDF)",
                data=pdf_bytes,
                file_name="business_model_primer.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.button(
                "Export Cheat Sheet (PDF)",
                disabled=True,
                use_container_width=True,
                help="Generate a primer first",
            )

    # ── Primer generation ─────────────────────────────────────────────────────
    if generate and description.strip():
        st.session_state.company_description = description.strip()
        st.session_state.messages = []  # reset chat on new primer
        st.divider()
        st.subheader("Primer")
        primer = stream_primer(client, description.strip())
        st.session_state.primer = primer
        st.rerun()

    # ── Display existing primer ───────────────────────────────────────────────
    if st.session_state.primer and not generate:
        st.divider()
        st.subheader("Primer")
        st.markdown(st.session_state.primer)

    # ── Chat section ──────────────────────────────────────────────────────────
    if st.session_state.primer:
        st.divider()
        st.subheader("Ask a follow-up")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask anything about this business model…")
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                reply = stream_chat(client, user_input)

            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()


if __name__ == "__main__":
    main()
