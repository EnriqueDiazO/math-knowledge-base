"""Synthetic, user-data-free fixtures shared by S5A runtime validation."""

from __future__ import annotations

from collections.abc import Iterable


def _pdf_literal(value: str) -> bytes:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode()


def synthetic_text_pdf(
    page_texts: Iterable[str] | None = None,
    *,
    padding_bytes: int = 320_000,
) -> bytes:
    """Build a valid multipage Helvetica PDF with selectable text and inert padding."""
    texts = tuple(
        page_texts
        or (
            "Advanced Reader page 1 - searchable theorem alpha",
            "Advanced Reader page 2 - searchable theorem beta",
            "Advanced Reader page 3 - searchable theorem gamma",
        )
    )
    if len(texts) < 2:
        raise ValueError("synthetic PDF requires at least two pages")
    if padding_bytes < 0:
        raise ValueError("padding_bytes cannot be negative")

    objects: dict[int, bytes] = {}
    page_numbers = [4 + index * 2 for index in range(len(texts))]
    kids = b" ".join(f"{number} 0 R".encode() for number in page_numbers)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = (
        b"<< /Type /Pages /Count " + str(len(texts)).encode() + b" /Kids [" + kids + b"] >>"
    )
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index, text in enumerate(texts):
        page_number = page_numbers[index]
        content_number = page_number + 1
        objects[page_number] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> "
            + f"/Contents {content_number} 0 R >>".encode()
        )
        content = (
            b"BT /F1 18 Tf 72 700 Td ("
            + _pdf_literal(text)
            + b") Tj ET\n"
            + b"BT /F1 11 Tf 72 665 Td (PDF page "
            + str(index + 1).encode()
            + b") Tj ET\n"
        )
        objects[content_number] = (
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream"
        )

    padding_number = max(objects) + 1
    padding = b"0" * padding_bytes
    objects[padding_number] = (
        b"<< /Length " + str(len(padding)).encode() + b" >>\nstream\n" + padding + b"\nendstream"
    )

    output = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = {0: 0}
    for number in range(1, padding_number + 1):
        offsets[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(objects[number])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {padding_number + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, padding_number + 1):
        output.extend(f"{offsets[number]:010d} 00000 n \n".encode())
    output.extend(
        b"trailer\n<< /Size "
        + str(padding_number + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return bytes(output)


__all__ = ["synthetic_text_pdf"]
