import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from utils import fmt_date, fmt_time

FORMATS = {
    "txt": ("text/plain; charset=utf-8", "txt"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "pdf": ("application/pdf", "pdf"),
}


def safe_filename(text: str, fallback: str = "catatan") -> str:
    base = re.sub(r"[^\w\- ]+", "", text or "", flags=re.UNICODE).strip().replace(" ", "_")
    return (base or fallback)[:60]


def _stamp(dt):
    return f"{fmt_date(dt)} {fmt_time(dt)}"


def notes_to_txt(notes) -> str:
    parts = []
    for n in notes:
        header = [n.title, "=" * min(len(n.title), 60)]
        meta = [f"Dibuat      : {_stamp(n.created_at)}"]
        if n.was_edited:
            meta.append(f"Diperbarui  : {_stamp(n.updated_at)}")
        if n.category:
            meta.append(f"Kategori    : {n.category.name}")
        parts.append("\n".join(header + meta + ["", n.content or "", ""]))
    return ("\n" + "-" * 60 + "\n\n").join(parts)


def notes_to_md(notes) -> str:
    parts = []
    for n in notes:
        meta = f"_Dibuat {_stamp(n.created_at)}"
        if n.was_edited:
            meta += f" · diperbarui {_stamp(n.updated_at)}"
        if n.category:
            meta += f" · {n.category.name}"
        parts.append(f"# {n.title}\n\n{meta}_\n\n{n.content or ''}\n")
    return "\n---\n\n".join(parts)


def _latin(text: str) -> str:
    return (text or "").encode("cp1252", "replace").decode("cp1252")


def notes_to_pdf(notes) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
        bottomMargin=18 * mm, title="MemoSpace", author="MemoSpace",
    )
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading1"], fontSize=18, leading=22, textColor=colors.HexColor("#1f2a44"))
    meta = ParagraphStyle("m", parent=ss["Normal"], fontSize=8.5, textColor=colors.HexColor("#6b7280"), spaceAfter=8)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=10.5, leading=15)

    story = []
    for i, n in enumerate(notes):
        if i:
            story += [Spacer(1, 8), HRFlowable(width="100%", color=colors.HexColor("#e5e7eb")), Spacer(1, 8)]
        story.append(Paragraph(escape(_latin(n.title)), h))
        line = f"Dibuat {_stamp(n.created_at)}"
        if n.was_edited:
            line += f" | diperbarui {_stamp(n.updated_at)}"
        if n.category:
            line += f" | {n.category.name}"
        story.append(Paragraph(escape(_latin(line)), meta))
        text = escape(_latin(n.content or "")).replace("\n", "<br/>")
        story.append(Paragraph(text or "&nbsp;", body))
    doc.build(story)
    return buf.getvalue()


def render(notes, fmt: str) -> bytes:
    if fmt == "txt":
        return notes_to_txt(notes).encode("utf-8")
    if fmt == "md":
        return notes_to_md(notes).encode("utf-8")
    if fmt == "pdf":
        return notes_to_pdf(notes)
    raise ValueError(fmt)
