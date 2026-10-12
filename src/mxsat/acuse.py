"""Read a SAT declaration receipt (acuse de recibo de la declaración provisional o definitiva) from its PDF.

What comes out: the period, the dates, each tax concept with its amounts, the total to pay and how long the
capture line is valid. What stays in: RFC, name, operation number and the capture line itself (the owner pays
with the PDF; the agent never needs it).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .errors import MxsatError
from .money import cents, dec, s2
from .privacy import Pseudonymizer

MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]


def _fold(text: str) -> str:
    """Lowercase without accents, so 'Período' and 'Periodo' match the same pattern."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()


def extract_text(path: str | Path) -> str:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        raise MxsatError("missing_dependency", "pdfplumber is required to read PDFs") from None
    try:
        with pdfplumber.open(str(path)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except FileNotFoundError:
        raise MxsatError("file_not_readable", "cannot read the file") from None
    except Exception:
        raise MxsatError("not_a_pdf", "the file is not a readable PDF") from None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    d, m, y = value.split("/")
    return f"{y}-{m}-{d}"


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(label)).strip("_")


def parse(text: str) -> tuple[dict, list[str]]:
    """Returns (fields with personal values, personal values)."""
    f = _fold(text)
    if "acuse de recibo" not in f or "declaracion" not in f:
        raise MxsatError("not_an_acuse", "the PDF is not a SAT declaration receipt")

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, f)
        return m.group(1).strip() if m else None

    def grab_raw(pattern: str) -> str | None:
        # same position in the original text, to keep capitals and accents of names
        m = re.search(pattern, f)
        return text[m.start(1):m.end(1)].strip() if m and len(f) == len(text) else (m.group(1).strip() if m else None)

    rfc = grab(r"rfc:\s*([a-z&n]{3,4}\d{6}[a-z0-9]{3})")
    name = grab_raw(r"nombre:\s*([^\n]+)")
    operation = grab(r"numero de operacion:\s*(\d+)")
    # The capture-line section is laid out in two columns, so labels and values interleave:
    # "línea de · importe total / <line> $<total> / captura: · a pagar:". Look for the shapes, not the labels.
    capture, section_total = None, None
    start = f.find("seccion linea de captura")
    if start < 0:
        start = f.find("linea de captura")
    if start >= 0:
        section = f[start:start + 600]
        for m in re.finditer(r"(?<![0-9a-z])([0-9a-z]{4}(?: ?[0-9a-z]{4}){4})(?![0-9a-z])", section):
            if sum(ch.isdigit() for ch in m.group(1)) >= 12:
                capture = m.group(1)
                break
        money = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", section)
        section_total = money.group(1) if money else None
    filed = re.search(r"fecha y hora de presentacion:\s*(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})", f)
    period = grab(r"periodo de la declaracion:\s*([a-z]+(?:\s*-\s*[a-z]+)?)")

    concepts = []
    body = f.split("sello digital")[0]
    blocks = re.split(r"concepto de pago\s*\d+:", body)[1:]
    original_blocks = None
    if len(f) == len(text):
        starts = [m.end() for m in re.finditer(r"concepto de pago\s*\d+:", body)]
        original_blocks = [text[s:] for s in starts]
    for i, block in enumerate(blocks):
        first, _, rest = block.partition("\n")
        concept_name = first.strip()
        if original_blocks:
            concept_name = original_blocks[i].partition("\n")[0].strip()
        amounts = {}
        for label, value in re.findall(r"^\s*([a-z][a-z ]+?):\s*\$?\s*(-?[\d,]+(?:\.\d+)?)\s*$", rest, re.MULTILINE):
            amounts[_slug(label)] = s2(dec(value))
        concepts.append({"concept": concept_name, "amounts": amounts})
    if not concepts:
        raise MxsatError("acuse_unreadable", "no tax concepts were found in the receipt")

    concepts_total = sum((dec(c["amounts"].get("cantidad_a_pagar", "0")) for c in concepts), dec("0"))
    total_to_pay = dec(section_total) if section_total else concepts_total
    if total_to_pay != concepts_total:
        raise MxsatError("acuse_inconsistent", "the total to pay differs from the sum of the concepts")

    month = None
    if period and period.split("-")[0].strip() in MONTHS_ES:
        month = MONTHS_ES.index(period.split("-")[0].strip()) + 1
    fields = {
        "rfc": rfc.upper() if rfc else None,
        "name": name,
        "operation": operation,
        "capture_line": capture,
        "declaration_type": grab(r"tipo de declaracion:\s*([a-z]+)"),
        "periodicity": grab(r"periodicidad:\s*([a-z]+)"),
        "period": period,
        "period_month": month,
        "fiscal_year": int(grab(r"ejercicio:\s*(\d{4})") or 0) or None,
        "filed_at": f"{_date(filed.group(1))}T{filed.group(2).zfill(5)}" if filed else None,
        "due_date": _date(grab(r"vencimiento obligacion:\s*(\d{2}/\d{2}/\d{4})")),
        "channel": grab(r"medio de presentacion:\s*([a-z]+)"),
        "concepts": concepts,
        "total_to_pay": s2(total_to_pay),
        "capture_line_valid_until": _date(grab(r"vigente hasta:\s*(\d{2}/\d{2}/\d{4})")),
    }
    personal = [v for v in (rfc, name, operation, capture) if v]
    if capture:
        personal.append(capture.replace(" ", ""))
    return fields, personal


def public_view(fields: dict, pz: Pseudonymizer) -> dict:
    return {
        "id": pz.id("acuse", fields["operation"]) if fields["operation"] else None,
        "kind": "declaration_receipt",
        "taxpayer_id": pz.party(fields["rfc"]) if fields["rfc"] else None,
        "declaration_type": fields["declaration_type"],
        "periodicity": fields["periodicity"],
        "period": fields["period"],
        "period_month": fields["period_month"],
        "fiscal_year": fields["fiscal_year"],
        "filed_at": fields["filed_at"],
        "due_date": fields["due_date"],
        "channel": fields["channel"],
        "concepts": fields["concepts"],
        "total_to_pay": fields["total_to_pay"],
        "total_to_pay_cents": cents(dec(fields["total_to_pay"])),
        "capture_line": "present" if fields["capture_line"] else None,
        "capture_line_valid_until": fields["capture_line_valid_until"],
    }


def read(path: str | Path, pz: Pseudonymizer) -> tuple[dict, list[str]]:
    fields, personal = parse(extract_text(path))
    return public_view(fields, pz), personal
