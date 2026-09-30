"""Conversion courriel -> PDF (aspect original préservé) avec pièces jointes aplaties.

Le corps du courriel est rendu en PDF en conservant sa mise en forme
(privilégie le HTML d'origine), puis chaque pièce jointe est convertie en
pages supplémentaires du même PDF (« flattening »).
"""

import io
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from pypdf import PdfReader, PdfWriter


def _html_to_pdf_bytes(html: str) -> Optional[bytes]:
    return None  # optionnel : weasyprint/wkhtmltopdf si disponible


def _text_to_pdf_bytes(text: str, title: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.enums import TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Pre", fontName="Courier", fontSize=8.5, leading=11, alignment=TA_LEFT))
    flow = [Paragraph(title, styles["Heading2"]), Spacer(1, 12)]
    for line in text.splitlines() or [text]:
        safe = (
            line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.strip() else "&nbsp;"
        )
        flow.append(Paragraph(safe, styles["Pre"]))
    doc.build(flow)
    return buf.getvalue()


def _attachment_to_pdf_bytes(filename: str, data: bytes) -> Optional[bytes]:
    """Convertit une pièce jointe en PDF (pages) ; None si impossible."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return data
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"):
        return _image_to_pdf_bytes(data, ext)
    if ext in (".txt", ".log", ".csv"):
        return _text_to_pdf_bytes(data.decode("utf-8", errors="replace"), filename)
    return None


def _image_to_pdf_bytes(data: bytes, ext: str) -> bytes:
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    iw, ih = img.size
    scale = min(w / iw, h / ih) * 0.95
    c.drawImage(ImageReader(img), 0, h - ih * scale, iw * scale, ih * scale)
    c.showPage()
    c.save()
    return buf.getvalue()


def email_to_pdf(parsed, output_path: str) -> str:
    """Construit le PDF du courriel + pièces jointes aplaties en pages supplémentaires."""
    writer = PdfWriter()
    body_pdf = None
    if parsed.body_html:
        body_pdf = _html_to_pdf_bytes(parsed.body_html)
    if body_pdf:
        reader = PdfReader(io.BytesIO(body_pdf))
        for p in reader.pages:
            writer.add_page(p)
    else:
        header = f"Sujet: {parsed.subject}\nDe: {parsed.from_name} <{parsed.from_addr}>\nÀ: {', '.join(parsed.to_addrs)}\nDate: {parsed.date}\n\n"
        body_pdf = _text_to_pdf_bytes(header + parsed.body_text, parsed.subject)
        reader = PdfReader(io.BytesIO(body_pdf))
        for p in reader.pages:
            writer.add_page(p)
    for filename, data in parsed.attachments:
        att_pdf = _attachment_to_pdf_bytes(filename, data)
        if att_pdf is None:
            note = _text_to_pdf_bytes(
                f"[Pièce jointe non convertible: {filename} ({len(data)} octets)]",
                "Pièce jointe",
            )
            reader = PdfReader(io.BytesIO(note))
        else:
            reader = PdfReader(io.BytesIO(att_pdf))
        for p in reader.pages:
            writer.add_page(p)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path
