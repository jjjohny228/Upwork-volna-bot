"""Plain-text <-> PDF helpers for resume storage.

Non-latin glyphs fall back to Helvetica's latin-1 range (MVP scope); resumes
are expected in English. Swap in a TTF font here if full unicode is needed.
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def text_to_pdf(text: str) -> bytes:
    """Render plain text into a simple wrapped-paragraph PDF, returning bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    style = getSampleStyleSheet()["Normal"]
    flowables: list = []
    for line in text.split("\n"):
        if line.strip():
            flowables.append(Paragraph(escape(line), style))
        else:
            flowables.append(Spacer(1, 12))
    if not flowables:
        flowables.append(Spacer(1, 12))
    doc.build(flowables)
    return buffer.getvalue()
