"""Minimal, dependency-free PDF writer (text pages, built-in Helvetica) for board-pack exports."""

from __future__ import annotations

PAGE_W, PAGE_H = 842, 595  # threshold-ok: A4 landscape in points
MARGIN = 48  # threshold-ok: layout constant


def _esc(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render(pages: list[list[tuple[str, int, bool]]], title: str = "", creator: str = "") -> bytes:
    """``pages`` = list of pages; each page is a list of (text, font_size, bold) lines."""
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 1 + 2 * len(pages)
    kids = []
    for lines in pages:
        y = PAGE_H - MARGIN
        ops = ["BT"]
        for text, size, is_bold in lines:
            y -= int(size * 1.5)
            ops.append(f"/{'F2' if is_bold else 'F1'} {size} Tf 1 0 0 1 {MARGIN} {y} Tm ({_esc(text)}) Tj")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add((f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                         f"/Resources << /Font << /F1 {font} 0 R /F2 {bold} 0 R >> >> /Contents {content} 0 R >>").encode()))
    add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode())
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info = add(f"<< /Title ({_esc(title)}) /Creator ({_esc(creator)}) >>".encode())
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
