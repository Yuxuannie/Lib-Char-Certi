#!/usr/bin/env python3
"""Render docs/USER_GUIDE.md to a shareable Word document (docs/USER_GUIDE.docx).

Why this exists: the User Guide is authored in Markdown, but it often needs to be
emailed as an attachment. This script does a self-contained Markdown -> Word
conversion using only the Python standard library (no pandoc / LibreOffice / pip
packages required). The resulting `.docx` is a single file with the screenshots
in `docs/images/` **embedded**, so it travels intact through email.

Usage:
    python scripts/make_user_guide_doc.py

Re-run it after replacing the placeholder screenshots so the real images are
embedded in the shared document.

Note on `.doc` vs `.docx`: this produces `.docx` (the modern Word format, opened
by Word 2007+, Outlook preview, Google Docs and LibreOffice). If you specifically
need a legacy `.doc`, open the `.docx` in Word and "Save As -> Word 97-2003".
"""

from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SRC_MD = DOCS / "USER_GUIDE.md"
OUT_DOCX = DOCS / "USER_GUIDE.docx"

EMU_PER_PX = 9525            # at 96 dpi
MAX_WIDTH_EMU = 5_486_400    # ~6 inches

_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_IMAGE_ONLY = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


# --------------------------------------------------------------------------- #
# Markdown -> block list
# --------------------------------------------------------------------------- #
def parse_blocks(md: str) -> list[dict]:
    lines = md.splitlines()
    blocks: list[dict] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append({"type": "code", "text": "\n".join(buf)})
            continue

        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            blocks.append({"type": "hr"})
            i += 1
            continue

        m = _IMAGE_ONLY.match(stripped)
        if m:
            blocks.append({"type": "image", "alt": m.group(1), "src": m.group(2).strip()})
            i += 1
            continue

        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2)})
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and re.match(r"\|[\s:|-]+\|", lines[i + 1].strip()):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "header": rows[0], "rows": rows[2:]})
            continue

        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            blocks.append({"type": "quote", "text": " ".join(b for b in buf if b.strip())})
            continue

        if re.match(r"[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "ul", "items": items})
            continue

        if re.match(r"\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "ol", "items": items})
            continue

        buf = []
        while i < n and lines[i].strip() and not lines[i].startswith("```") \
                and not lines[i].strip().startswith(("#", ">", "|", "---")) \
                and not re.match(r"[-*]\s+|\d+\.\s+", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        blocks.append({"type": "para", "text": " ".join(buf)})

    return blocks


# --------------------------------------------------------------------------- #
# Inline runs
# --------------------------------------------------------------------------- #
def inline_runs(text: str) -> str:
    """Return <w:r> run XML for a line, honouring **bold** and `code`.

    Markdown links are flattened to their label text. Images are handled at the
    block level, not here.
    """
    text = _LINK.sub(lambda m: m.group(1), text)

    # tokenize into (kind, value): kind in {plain, bold, code}
    tokens: list[tuple[str, str]] = []
    pos = 0
    pattern = re.compile(r"\*\*([^*]+)\*\*|`([^`]+)`")
    for m in pattern.finditer(text):
        if m.start() > pos:
            tokens.append(("plain", text[pos:m.start()]))
        if m.group(1) is not None:
            tokens.append(("bold", m.group(1)))
        else:
            tokens.append(("code", m.group(2)))
        pos = m.end()
    if pos < len(text):
        tokens.append(("plain", text[pos:]))

    runs = []
    for kind, value in tokens:
        if value == "":
            continue
        props = []
        if kind == "bold":
            props.append("<w:b/>")
        if kind == "code":
            props.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
            props.append('<w:shd w:val="clear" w:fill="F2F2F2"/>')
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(value)}</w:t></w:r>')
    return "".join(runs)


# --------------------------------------------------------------------------- #
# PNG size
# --------------------------------------------------------------------------- #
def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return (640, 360)
    w, h = struct.unpack(">II", data[16:24])
    return (w, h)


# --------------------------------------------------------------------------- #
# Block -> docx body XML
# --------------------------------------------------------------------------- #
class DocxBuilder:
    def __init__(self) -> None:
        self.body: list[str] = []
        self.images: list[tuple[str, Path]] = []   # (rId, path)
        self._next_rid = 1
        self._next_img = 1

    def _rid(self) -> str:
        rid = f"rId{self._next_rid}"
        self._next_rid += 1
        return rid

    def para(self, runs_xml: str, style: str | None = None,
             extra_ppr: str = "") -> None:
        ppr = ""
        if style or extra_ppr:
            style_xml = '<w:pStyle w:val="%s"/>' % style if style else ""
            ppr = "<w:pPr>%s%s</w:pPr>" % (style_xml, extra_ppr)
        self.body.append(f"<w:p>{ppr}{runs_xml}</w:p>")

    def add_heading(self, level: int, text: str) -> None:
        self.para(inline_runs(text), style=f"Heading{min(level, 4)}")

    def add_para(self, text: str) -> None:
        self.para(inline_runs(text))

    def add_quote(self, text: str) -> None:
        ppr = ('<w:pBdr><w:left w:val="single" w:sz="18" w:space="8" '
               'w:color="BBBBBB"/></w:pBdr><w:ind w:left="240"/>')
        self.para(inline_runs(text), extra_ppr=ppr)

    def add_code(self, text: str) -> None:
        for ln in text.split("\n"):
            run = (f'<w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
                   f'<w:shd w:val="clear" w:fill="F4F4F4"/></w:rPr>'
                   f'<w:t xml:space="preserve">{escape(ln) or " "}</w:t></w:r>')
            self.para(run, extra_ppr='<w:shd w:val="clear" w:fill="F4F4F4"/>')

    def add_list(self, items: list[str], ordered: bool) -> None:
        num = "2" if ordered else "1"
        for it in items:
            ppr = (f'<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/>'
                   f'</w:numPr></w:pPr>')
            self.body.append(f"<w:p>{ppr}{inline_runs(it)}</w:p>")

    def add_hr(self) -> None:
        self.body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                         'w:space="1" w:color="CCCCCC"/></w:pBdr></w:pPr></w:p>')

    def add_table(self, header: list[str], rows: list[list[str]]) -> None:
        cols = max(len(header), *(len(r) for r in rows)) if rows else len(header)
        grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(cols))
        out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
               '<w:tblW w:w="0" w:type="auto"/>'
               '<w:tblBorders>'
               '<w:top w:val="single" w:sz="4" w:color="999999"/>'
               '<w:left w:val="single" w:sz="4" w:color="999999"/>'
               '<w:bottom w:val="single" w:sz="4" w:color="999999"/>'
               '<w:right w:val="single" w:sz="4" w:color="999999"/>'
               '<w:insideH w:val="single" w:sz="4" w:color="999999"/>'
               '<w:insideV w:val="single" w:sz="4" w:color="999999"/>'
               '</w:tblBorders></w:tblPr>',
               f"<w:tblGrid>{grid}</w:tblGrid>"]

        def row_xml(cells: list[str], head: bool) -> str:
            tcs = []
            for c in range(cols):
                val = cells[c] if c < len(cells) else ""
                shd = '<w:shd w:val="clear" w:fill="EEEEEE"/>' if head else ""
                runs = inline_runs(("**" + val + "**") if head and val else val)
                tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/>{shd}'
                           f'</w:tcPr><w:p>{runs}</w:p></w:tc>')
            return f"<w:tr>{''.join(tcs)}</w:tr>"

        out.append(row_xml(header, True))
        for r in rows:
            out.append(row_xml(r, False))
        out.append("</w:tbl>")
        # a trailing empty paragraph keeps Word happy after a table
        out.append("<w:p/>")
        self.body.append("".join(out))

    def add_image(self, src: str, alt: str) -> None:
        path = (DOCS / src).resolve()
        if not path.is_file():
            self.add_para(f"[missing image: {src}]")
            return
        rid = self._rid()
        self.images.append((rid, path))
        px_w, px_h = png_size(path)
        emu_w = px_w * EMU_PER_PX
        emu_h = px_h * EMU_PER_PX
        if emu_w > MAX_WIDTH_EMU:
            emu_h = int(emu_h * MAX_WIDTH_EMU / emu_w)
            emu_w = MAX_WIDTH_EMU
        did = self._next_img
        self._next_img += 1
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{emu_w}" cy="{emu_h}"/>'
            f'<wp:docPr id="{did}" name="Picture {did}" descr="{escape(alt)}"/>'
            f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:nvPicPr><pic:cNvPr id="{did}" name="img{did}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{emu_w}" cy="{emu_h}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        )
        self.body.append(f"<w:p>{drawing}</w:p>")

    def render(self, blocks: list[dict]) -> None:
        for b in blocks:
            t = b["type"]
            if t == "heading":
                self.add_heading(b["level"], b["text"])
            elif t == "para":
                self.add_para(b["text"])
            elif t == "quote":
                self.add_quote(b["text"])
            elif t == "code":
                self.add_code(b["text"])
            elif t == "ul":
                self.add_list(b["items"], ordered=False)
            elif t == "ol":
                self.add_list(b["items"], ordered=True)
            elif t == "table":
                self.add_table(b["header"], b["rows"])
            elif t == "image":
                self.add_image(b["src"], b["alt"])
            elif t == "hr":
                self.add_hr()


# --------------------------------------------------------------------------- #
# OOXML package
# --------------------------------------------------------------------------- #
def build_docx(builder: DocxBuilder, out: Path) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<w:body>{"".join(builder.body)}'
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        '</w:body></w:document>'
    )

    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStyles" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '<Relationship Id="rIdNum" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" '
            'Target="numbering.xml"/>']
    for rid, path in builder.images:
        rels.append(f'<Relationship Id="{rid}" '
                    f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    f'Target="media/{path.name}"/>')
    rels.append("</Relationships>")

    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Default Extension="png" ContentType="image/png"/>'
                     '<Override PartName="/word/document.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/numbering.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                     '</Types>']

    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="word/document.xml"/></Relationships>')

    def heading_style(num: int, size: int, color: str) -> str:
        return (f'<w:style w:type="paragraph" w:styleId="Heading{num}">'
                f'<w:name w:val="heading {num}"/><w:basedOn w:val="Normal"/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/></w:pPr>'
                f'<w:rPr><w:b/><w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr></w:style>')

    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>'
        '</w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        + heading_style(1, 40, "1F3864")
        + heading_style(2, 32, "2E5496")
        + heading_style(3, 26, "2E5496")
        + heading_style(4, 24, "444444")
        + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
          '<w:tblPr><w:tblBorders>'
          '<w:top w:val="single" w:sz="4" w:color="999999"/>'
          '<w:left w:val="single" w:sz="4" w:color="999999"/>'
          '<w:bottom w:val="single" w:sz="4" w:color="999999"/>'
          '<w:right w:val="single" w:sz="4" w:color="999999"/>'
          '<w:insideH w:val="single" w:sz="4" w:color="999999"/>'
          '<w:insideV w:val="single" w:sz="4" w:color="999999"/>'
          '</w:tblBorders></w:tblPr></w:style>'
        '</w:styles>'
    )

    numbering = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/>'
        '<w:lvlText w:val="&#8226;"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
        '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
        '<w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
        '</w:numbering>'
    )

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", "".join(rels))
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
        for _rid, path in builder.images:
            z.write(path, f"word/media/{path.name}")


def main() -> int:
    if not SRC_MD.is_file():
        print(f"ERROR: {SRC_MD} not found.")
        return 2
    blocks = parse_blocks(SRC_MD.read_text(encoding="utf-8"))
    builder = DocxBuilder()
    builder.render(blocks)
    build_docx(builder, OUT_DOCX)
    n_img = len(builder.images)
    print(f"wrote {OUT_DOCX}  ({n_img} image(s) embedded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
