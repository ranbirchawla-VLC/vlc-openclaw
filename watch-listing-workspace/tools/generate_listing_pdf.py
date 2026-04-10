#!/usr/bin/env python3
"""
generate_listing_pdf.py — Generate a clean, formatted PDF from a watch listing markdown file.

Usage:
  python3 generate_listing_pdf.py <path_to_listing.md>
  python3 generate_listing_pdf.py <folder_containing_listing_*.md>

Output: listing-<SKU>.pdf in the same folder as the markdown file.
"""

import sys
import os
import re
import json

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── Styles ────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()

    styles = {
        "h1": ParagraphStyle("h1",
            fontName="Helvetica-Bold", fontSize=16,
            leading=20, spaceAfter=4, spaceBefore=12,
            alignment=TA_CENTER),

        "h2": ParagraphStyle("h2",
            fontName="Helvetica-Bold", fontSize=13,
            leading=17, spaceAfter=4, spaceBefore=14,
            textColor=colors.black),

        "h3": ParagraphStyle("h3",
            fontName="Helvetica-Bold", fontSize=11,
            leading=14, spaceAfter=3, spaceBefore=10,
            textColor=colors.black),

        "body": ParagraphStyle("body",
            fontName="Helvetica", fontSize=9,
            leading=13, spaceAfter=4),

        "bold": ParagraphStyle("bold",
            fontName="Helvetica-Bold", fontSize=9,
            leading=13, spaceAfter=4),

        "bullet": ParagraphStyle("bullet",
            fontName="Helvetica", fontSize=9,
            leading=13, spaceAfter=2,
            leftIndent=16, bulletIndent=4),

        "checkbox": ParagraphStyle("checkbox",
            fontName="Helvetica", fontSize=9,
            leading=13, spaceAfter=2,
            leftIndent=16),

        "code": ParagraphStyle("code",
            fontName="Courier", fontSize=8,
            leading=12, spaceAfter=2,
            leftIndent=20),

        "hr": ParagraphStyle("hr", spaceAfter=4),
    }
    return styles


# ── Markdown parser ───────────────────────────────────────────────────────────

def escape_xml(text):
    """Escape characters that break ReportLab's XML parser."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def inline_format(text):
    """Convert inline markdown (bold, italic, code) to ReportLab XML."""
    text = escape_xml(text)
    # Bold+italic ***text***
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic *text*
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # Code `text`
    text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)
    return text


def parse_table(lines, styles):
    """Parse a markdown table and return a ReportLab Table flowable."""
    rows = []
    for line in lines:
        if re.match(r"^\s*\|[-:| ]+\|\s*$", line):
            continue  # separator row
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return None

    col_count = max(len(r) for r in rows)
    # Pad rows
    data = []
    for i, row in enumerate(rows):
        padded = row + [""] * (col_count - len(row))
        style = "Helvetica-Bold" if i == 0 else "Helvetica"
        data.append([
            Paragraph(inline_format(cell), ParagraphStyle(
                "tc", fontName=style, fontSize=8.5, leading=12))
            for cell in padded
        ])

    col_width = (6.5 * inch) / col_count
    t = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#E8E8E8")),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def md_to_flowables(md_text, styles):
    """Convert markdown text to a list of ReportLab flowables."""
    flowables = []
    lines = md_text.splitlines()
    i = 0
    pending_table = []
    in_table = False

    def flush_table():
        nonlocal pending_table, in_table
        if pending_table:
            t = parse_table(pending_table, styles)
            if t:
                flowables.append(Spacer(1, 4))
                flowables.append(t)
                flowables.append(Spacer(1, 6))
        pending_table = []
        in_table = False

    while i < len(lines):
        line = lines[i]

        # Table row
        if line.strip().startswith("|"):
            # Peek ahead: if there's no separator row (|---|) following, it's a Key Details pipe line
            # Key Details: single content row with no header/separator — render as wrapped paragraph
            next_line = lines[i+1].strip() if i+1 < len(lines) else ""
            is_separator = bool(re.match(r"^\s*\|[-:| ]+\|\s*$", next_line))
            is_already_separator = bool(re.match(r"^\s*\|[-:| ]+\|\s*$", line.strip()))
            if not in_table and not is_separator and not is_already_separator:
                # Single pipe line — render as Key Details paragraph
                cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
                kd_text = "  |  ".join(cells)
                kd_style = ParagraphStyle("keydetails",
                    fontName="Helvetica", fontSize=8.5,
                    leading=14, spaceAfter=6, spaceBefore=2,
                    leftIndent=0, borderPad=4,
                    textColor=colors.HexColor("#222222"))
                flowables.append(Paragraph(escape_xml(kd_text), kd_style))
                i += 1
                continue
            in_table = True
            pending_table.append(line)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # Blank line
        if not line.strip():
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # HR ---
        if re.match(r"^\s*---+\s*$", line):
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")))
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # H1 #
        m = re.match(r"^# (.+)$", line)
        if m:
            flowables.append(Paragraph(inline_format(m.group(1)), styles["h1"]))
            i += 1
            continue

        # H2 ##
        m = re.match(r"^## (.+)$", line)
        if m:
            heading_text = m.group(1)
            # Special style for INTERNAL / DO NOT POST sections
            if re.search(r'INTERNAL|DO NOT POST', heading_text, re.IGNORECASE):
                flowables.append(Spacer(1, 8))
                internal_style = ParagraphStyle(
                    "h2_internal",
                    fontName="Helvetica-Bold",
                    fontSize=11,
                    leading=16,
                    spaceAfter=4,
                    spaceBefore=4,
                    textColor=colors.HexColor("#7B0000"),
                    backColor=colors.HexColor("#FFF0F0"),
                    borderPad=6,
                )
                label = f"⚠ {inline_format(heading_text)}"
                t = Table([[Paragraph(label, internal_style)]], colWidths=[6.5 * inch])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FFF0F0")),
                    ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#CC0000")),
                    ("TOPPADDING", (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING", (0,0), (-1,-1), 8),
                    ("RIGHTPADDING", (0,0), (-1,-1), 8),
                ]))
                flowables.append(t)
                flowables.append(Spacer(1, 4))
            else:
                flowables.append(Spacer(1, 6))
                flowables.append(HRFlowable(width="100%", thickness=1, color=colors.black))
                flowables.append(Paragraph(inline_format(heading_text), styles["h2"]))
            i += 1
            continue

        # H3 ###
        m = re.match(r"^### (.+)$", line)
        if m:
            flowables.append(Paragraph(inline_format(m.group(1)), styles["h3"]))
            i += 1
            continue

        # Checkbox - [ ] or - [x]
        m = re.match(r"^\s*-\s+\[( |x|X)\]\s+(.+)$", line)
        if m:
            checked = "x" if m.group(1).lower() == "x" else " "
            box = "☑" if checked == "x" else "☐"
            flowables.append(Paragraph(
                f"{box}  {inline_format(m.group(2))}", styles["checkbox"]))
            i += 1
            continue

        # Bullet - item
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            flowables.append(Paragraph(
                f"• {inline_format(m.group(1))}", styles["bullet"]))
            i += 1
            continue

        # Numbered list
        m = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if m:
            flowables.append(Paragraph(
                f"{inline_format(line.strip())}", styles["bullet"]))
            i += 1
            continue

        # Bold line (whole line is **text**)
        m = re.match(r"^\*\*(.+)\*\*$", line.strip())
        if m:
            flowables.append(Paragraph(inline_format(line.strip()), styles["bold"]))
            i += 1
            continue

        # Blockquote > text
        m = re.match(r"^>\s*(.+)$", line)
        if m:
            bq_style = ParagraphStyle("blockquote",
                fontName="Helvetica-Oblique", fontSize=8.5,
                leading=13, spaceAfter=4, spaceBefore=2,
                leftIndent=16, borderPad=4,
                textColor=colors.HexColor("#555555"))
            flowables.append(Paragraph(inline_format(m.group(1)), bq_style))
            i += 1
            continue

        # Default: body text
        flowables.append(Paragraph(inline_format(line.strip()), styles["body"]))
        i += 1

    if in_table:
        flush_table()

    return flowables


# ── Main ──────────────────────────────────────────────────────────────────────

def find_md_file(path):
    if os.path.isfile(path) and path.endswith(".md"):
        return path
    if os.path.isdir(path):
        md_files = [f for f in os.listdir(path) if f.endswith(".md")]
        if not md_files:
            return None
        # Prefer the newest .md file by modification time
        md_files_with_mtime = [
            (f, os.path.getmtime(os.path.join(path, f)))
            for f in md_files
        ]
        md_files_with_mtime.sort(key=lambda x: x[1], reverse=True)
        return os.path.join(path, md_files_with_mtime[0][0])
    return None


def generate_pdf(md_path):
    folder = os.path.dirname(md_path)
    basename = os.path.splitext(os.path.basename(md_path))[0]
    pdf_path = os.path.join(folder, basename + ".pdf")

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    styles = build_styles()
    flowables = md_to_flowables(md_text, styles)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
    )
    doc.build(flowables)
    return pdf_path


def main():
    # Accept input from stdin (JSON) or command-line argument
    path = None
    if len(sys.argv) >= 2:
        path = sys.argv[1]
    else:
        try:
            raw = sys.stdin.read().strip()
            if raw:
                data = json.loads(raw)
                path = data.get("folder_or_md_path")
        except Exception:
            pass

    if not path:
        print(json.dumps({"ok": False, "error": "No path provided. Pass folder_or_md_path in JSON via stdin or as CLI argument."}))
        sys.exit(1)

    md_path = find_md_file(path)

    if not md_path:
        print(json.dumps({"ok": False, "error": f"No listing .md file found at: {path}"}))
        sys.exit(1)

    try:
        pdf_path = generate_pdf(md_path)
        print(json.dumps({"ok": True, "pdf_path": pdf_path, "md_path": md_path}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
