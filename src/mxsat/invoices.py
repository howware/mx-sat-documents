"""Templates, drafts and verification of invoices to be captured in the SAT portal.

A template is taken from a real, stamped invoice: who it is for, the concept and its taxes. It lives in the
private store. A draft is a template applied to an amount, a date and (when the description names a month) a
period: the exact numbers and a capture sheet the owner copies into the portal. Verification compares the
stamped XML against the approved draft, field by field.

None of this holds tax rules. Whether an income is taxed at 0 %, exempt or with withholdings is decided by the
owner and their accountant; it arrives here inside the template, copied from an invoice they already issued.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from . import catalogs as cat
from .errors import MxsatError
from .money import (
    CENT,
    add_months,
    cents,
    dec,
    last_day,
    months_between,
    parse_date,
    parse_period,
    r2,
    s2,
)
from .privacy import GENERIC_RFCS, Pseudonymizer, norm, rfc_kind
from .store import Store

MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"],
}
MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS["es"] + MONTHS["en"] + ["setiembre"]) + r")\b", re.IGNORECASE)
TOKENS = ("{first_day_02}", "{first_day}", "{last_day}", "{MONTH}", "{Month}", "{month}", "{year}")

COMPROBANTE_KEYS = ("Version", "Serie", "TipoDeComprobante", "Moneda", "Exportacion", "MetodoPago", "FormaPago",
                    "LugarExpedicion")
CONCEPTO_KEYS = ("ClaveProdServ", "NoIdentificacion", "Cantidad", "ClaveUnidad", "Unidad", "Descripcion",
                 "ObjetoImp")


# -- description periods ---------------------------------------------------------------------------------

def detect_period(desc: str, issued: dt.date) -> tuple[str, dict | None]:
    """Turn 'del 1 al 31 de Octubre de 2026' into placeholders, and learn the offset from the issue month."""
    m = MONTH_RE.search(desc)
    if not m:
        return desc, None
    word = m.group(1)
    low = "septiembre" if word.lower() == "setiembre" else word.lower()
    lang = "es" if low in MONTHS["es"] else "en"
    month = MONTHS[lang].index(low) + 1
    token = "{MONTH}" if word.isupper() else "{Month}" if word[0].isupper() else "{month}"
    spans: list[tuple[int, int, str]] = [(m.start(), m.end(), token)]
    placeholders = ["month"]

    ym = re.match(r"(\s*(?:de|del|of|,)?\s*)(20\d{2})\b", desc[m.end():m.end() + 14], re.IGNORECASE)
    if ym:
        year = int(ym.group(2))
        spans.append((m.end() + ym.start(2), m.end() + ym.end(2), "{year}"))
        placeholders.append("year")
    else:
        year = min((issued.year - 1, issued.year, issued.year + 1),
                   key=lambda y: abs(months_between((issued.year, issued.month), (y, month))))

    lo = max(0, m.start() - 30)
    dr = re.search(r"\b(0?1)(\s*(?:al|a|-|–|to|through)\s*)(\d{2})\b(?=\D*$)", desc[lo:m.start()], re.IGNORECASE)
    if dr and int(dr.group(3)) == last_day(year, month):
        first = "{first_day_02}" if dr.group(1) == "01" else "{first_day}"
        spans.append((lo + dr.start(1), lo + dr.end(1), first))
        spans.append((lo + dr.start(3), lo + dr.end(3), "{last_day}"))
        placeholders.append("day_range")

    text = desc
    for start, end, tok in sorted(spans, reverse=True):
        text = text[:start] + tok + text[end:]
    info = {
        "lang": lang,
        "offset_months": months_between((issued.year, issued.month), (year, month)),
        "placeholders": sorted(placeholders),
    }
    return text, info


def render_description(text: str, period: tuple[int, int] | None, lang: str = "es") -> str:
    if period is None:
        return text
    year, month = period
    name = MONTHS[lang][month - 1]
    values = {
        "{first_day_02}": "01", "{first_day}": "1", "{last_day}": str(last_day(year, month)),
        "{MONTH}": name.upper(), "{Month}": name.capitalize(), "{month}": name, "{year}": str(year),
    }
    for tok in TOKENS:
        text = text.replace(tok, values[tok])
    return text


# -- coherence with the CFDI 4.0 rules -------------------------------------------------------------------

def rule_problems(comprobante: dict, receptor: dict, concepto: dict, traslados: list, retenciones: list) -> list[str]:
    """Problems against a subset of the CFDI 4.0 rules. Messages never include personal values."""
    p: list[str] = []
    for key, catalog in (("FormaPago", cat.FORMA_PAGO), ("MetodoPago", cat.METODO_PAGO),
                         ("Exportacion", cat.EXPORTACION)):
        if comprobante.get(key) not in catalog:
            p.append(f"{key} is not in the SAT catalog")
    if receptor.get("UsoCFDI") not in cat.USO_CFDI:
        p.append("UsoCFDI is not in the SAT catalog")
    if receptor.get("RegimenFiscalReceptor") not in cat.REGIMEN_FISCAL:
        p.append("RegimenFiscalReceptor is not in the SAT catalog")
    if concepto.get("ObjetoImp") not in cat.OBJETO_IMP:
        p.append("ObjetoImp is not in the SAT catalog")
    if comprobante.get("MetodoPago") == "PPD" and comprobante.get("FormaPago") != "99":
        p.append("MetodoPago PPD requires FormaPago 99")
    if comprobante.get("MetodoPago") == "PUE" and comprobante.get("FormaPago") == "99":
        p.append("MetodoPago PUE cannot use FormaPago 99")
    rfc = norm(receptor.get("Rfc", ""))
    if rfc in GENERIC_RFCS:
        if receptor.get("UsoCFDI") != "S01":
            p.append("a generic RFC requires UsoCFDI S01")
        if receptor.get("RegimenFiscalReceptor") != "616":
            p.append("a generic RFC requires RegimenFiscalReceptor 616")
        if receptor.get("DomicilioFiscalReceptor") != comprobante.get("LugarExpedicion"):
            p.append("with a generic RFC, DomicilioFiscalReceptor must equal LugarExpedicion")
    if rfc == "XEXX010101000" and not (receptor.get("ResidenciaFiscal") and receptor.get("NumRegIdTrib")):
        p.append("a foreign receiver needs ResidenciaFiscal and NumRegIdTrib")
    taxed = bool(traslados or retenciones)
    if concepto.get("ObjetoImp") == "02" and not taxed:
        p.append("ObjetoImp 02 requires taxes on the concept")
    if concepto.get("ObjetoImp") in ("01", "03", "04") and taxed:
        p.append("this ObjetoImp does not allow taxes on the concept")
    for t in traslados + retenciones:
        if t.get("Impuesto") not in cat.IMPUESTO:
            p.append("unknown Impuesto")
        if t.get("TipoFactor") == "Cuota":
            p.append("TipoFactor Cuota is not supported")
    for t in retenciones:
        if t.get("TipoFactor") != "Tasa":
            p.append("withholdings must use TipoFactor Tasa")
    return p


# -- templates -------------------------------------------------------------------------------------------

def template_from_cfdi(raw: dict, name: str) -> tuple[dict, list[str]]:
    Store.check_name(name)
    comp = raw["comprobante"]
    if raw["version"] != "4.0":
        raise MxsatError("unsupported_cfdi", "templates need a CFDI 4.0")
    if comp.get("TipoDeComprobante") != "I":
        raise MxsatError("unsupported_cfdi", "templates need an income (I) invoice")
    if len(raw["conceptos"]) != 1:
        raise MxsatError("unsupported_cfdi", "templates support invoices with exactly one concept in this version")
    if comp.get("Moneda") != "MXN":
        raise MxsatError("unsupported_cfdi", "templates support MXN invoices in this version")
    if raw["informacion_global"]:
        raise MxsatError("unsupported_cfdi", "global invoices are not supported in this version")
    c = raw["conceptos"][0]
    if c["terceros"] or c["partes"] or c["aduana"]:
        raise MxsatError("unsupported_cfdi", "concepts with third parties, parts or customs data are not supported")
    if dec(c["attrs"].get("Cantidad", "1")) != 1:
        raise MxsatError("unsupported_cfdi", "templates need a concept with quantity 1")
    issued = parse_date((comp.get("Fecha") or "")[:10], "Fecha")

    concepto = {k: c["attrs"][k] for k in CONCEPTO_KEYS if c["attrs"].get(k)}
    text, period = detect_period(concepto.get("Descripcion", ""), issued)
    concepto["Descripcion"] = text
    keep = ("Impuesto", "TipoFactor", "TasaOCuota")
    traslados = [{k: t[k] for k in keep if t.get(k)} for t in c["impuestos"]["traslados"]]
    retenciones = [{k: t[k] for k in keep if t.get(k)} for t in c["impuestos"]["retenciones"]]
    template = {
        "name": name,
        "source": {"series": comp.get("Serie"), "folio": comp.get("Folio"), "issued_at": comp.get("Fecha")},
        "comprobante": {k: comp[k] for k in COMPROBANTE_KEYS if comp.get(k)},
        "emisor": dict(raw["emisor"]),
        "receptor": dict(raw["receptor"]),
        "concepto": concepto,
        "period": period,
        "traslados": traslados,
        "retenciones": retenciones,
        "cuenta_predial": list(c["cuenta_predial"]),
    }
    warnings = rule_problems(template["comprobante"], template["receptor"], concepto, traslados, retenciones)
    return template, warnings


def template_personal(t: dict) -> list[str]:
    return [
        t["comprobante"].get("LugarExpedicion", ""), t["emisor"].get("Rfc", ""), t["emisor"].get("Nombre", ""),
        t["receptor"].get("Rfc", ""), t["receptor"].get("Nombre", ""),
        t["receptor"].get("DomicilioFiscalReceptor", ""), t["receptor"].get("NumRegIdTrib", ""),
        t["concepto"].get("Descripcion", ""), t["concepto"].get("NoIdentificacion", ""), *t["cuenta_predial"],
    ]


def _tax_view(t: dict) -> dict:
    out = {"tax": cat.IMPUESTO.get(t.get("Impuesto", ""), t.get("Impuesto")), "factor": t.get("TipoFactor"),
           "rate": t.get("TasaOCuota")}
    if "Base" in t:
        out["base"] = t["Base"]
    if t.get("TipoFactor") != "Exento" and "Base" in t:
        out["amount"] = t.get("Importe")
    return out


def template_view(t: dict, pz: Pseudonymizer, warnings: list[str] | None = None) -> dict:
    r, c, comp = t["receptor"], t["concepto"], t["comprobante"]
    view = {
        "name": t["name"],
        "receiver_id": pz.party(r.get("Rfc"), r.get("Nombre"), r.get("NumRegIdTrib")),
        "receiver_rfc_kind": rfc_kind(r.get("Rfc")),
        "receiver_regime": r.get("RegimenFiscalReceptor"),
        "use": r.get("UsoCFDI"),
        "tax_residence": r.get("ResidenciaFiscal"),
        "issuer_id": pz.party(t["emisor"].get("Rfc")),
        "issuer_regime": t["emisor"].get("RegimenFiscal"),
        "series": comp.get("Serie"),
        "currency": comp.get("Moneda"),
        "payment_form": comp.get("FormaPago"),
        "payment_method": comp.get("MetodoPago"),
        "export": comp.get("Exportacion"),
        "product_code": c.get("ClaveProdServ"),
        "unit_code": c.get("ClaveUnidad"),
        "tax_object": c.get("ObjetoImp"),
        "transfers": [_tax_view(x) for x in t["traslados"]],
        "withholdings": [_tax_view(x) for x in t["retenciones"]],
        "property_tax_accounts": len(t["cuenta_predial"]),
        "period": t["period"],
        "source": t["source"],
    }
    if warnings is not None:
        view["warnings"] = warnings
    return view


# -- drafts ----------------------------------------------------------------------------------------------

def _apply_taxes(subtotal: Decimal, template: dict) -> tuple[list[dict], list[dict], Decimal]:
    traslados, retenciones = [], []
    total = subtotal
    for t in template["traslados"]:
        row = {**t, "Base": s2(subtotal)}
        if t["TipoFactor"] != "Exento":
            amount = r2(subtotal * dec(t["TasaOCuota"]))
            row["Importe"] = s2(amount)
            total += amount
        traslados.append(row)
    for t in template["retenciones"]:
        amount = r2(subtotal * dec(t["TasaOCuota"]))
        retenciones.append({**t, "Base": s2(subtotal), "Importe": s2(amount)})
        total -= amount
    return traslados, retenciones, total


def amounts_for(template: dict, *, subtotal: str | None = None, total: str | None = None) -> dict:
    """Exact amounts. From a total (what reached the bank), find the subtotal whose taxes, rounded to cents
    as the portal does, give exactly that total."""
    if (subtotal is None) == (total is None):
        raise MxsatError("bad_amount", "give exactly one of --total or --subtotal")
    if subtotal is not None:
        s = r2(dec(subtotal, "subtotal"))
        if s <= 0:
            raise MxsatError("bad_amount", "subtotal must be positive")
        traslados, retenciones, t = _apply_taxes(s, template)
        return {"subtotal": s, "traslados": traslados, "retenciones": retenciones, "total": t}
    target = r2(dec(total, "total"))
    if target <= 0:
        raise MxsatError("bad_amount", "total must be positive")
    factor = Decimal(1)
    for t in template["traslados"]:
        if t["TipoFactor"] != "Exento":
            factor += dec(t["TasaOCuota"])
    for t in template["retenciones"]:
        factor -= dec(t["TasaOCuota"])
    guess = r2(target / factor)
    nearest = []
    for delta in sorted(range(-6, 7), key=abs):
        s = guess + delta * CENT
        if s <= 0:
            continue
        traslados, retenciones, t = _apply_taxes(s, template)
        if t == target:
            return {"subtotal": s, "traslados": traslados, "retenciones": retenciones, "total": t}
        nearest.append((abs(t - target), s2(t), s2(s)))
    near = ", ".join(f"total {t} (subtotal {s})" for _, t, s in sorted(nearest)[:2])
    raise MxsatError("no_exact_subtotal", f"no subtotal gives exactly this total after rounding; nearest: {near}")


def next_folio(store: Store, series: str) -> int:
    last = store.state()["last_folio"].get(series)
    used = [int(d["comprobante"]["Folio"]) for d in store.drafts()
            if d["comprobante"].get("Serie", "") == series and d["comprobante"]["Folio"].isdigit()]
    known = [x for x in [last, *used] if x is not None]
    if not known:
        raise MxsatError("unknown_folio", "no previous folio is known for this series; pass --folio")
    return max(known) + 1


def build_draft(store: Store, name: str, *, total: str | None = None, subtotal: str | None = None,
                date: str | None = None, period: str | None = None, folio: str | None = None,
                ref: str | None = None, replace: bool = False, today: dt.date | None = None) -> tuple[dict, bool]:
    """Returns (draft, unchanged). A ``ref`` (e.g. the bank deposit id) makes it idempotent and guards against
    invoicing the same deposit twice."""
    template = store.load_template(name)
    day = parse_date(date) if date else (today or dt.date.today())
    pinfo = template.get("period")
    if pinfo:
        per = parse_period(period) if period else add_months(day.year, day.month, pinfo["offset_months"])
    elif period:
        raise MxsatError("no_period", "this template's description has no month to fill in")
    else:
        per = None
    if folio is not None and not folio.isdigit():
        raise MxsatError("bad_folio", "folio must be digits")
    if ref is not None and not re.match(r"^[\w.:-]{1,80}$", ref):
        raise MxsatError("bad_ref", "ref must be 1-80 letters, digits, '.', ':', '_' or '-'")

    request = {"template": name, "total": total, "subtotal": subtotal, "date": day.isoformat(),
               "period": f"{per[0]:04d}-{per[1]:02d}" if per else None, "folio": folio}
    series = template["comprobante"].get("Serie", "")
    if ref:
        existing = next((d for d in store.drafts() if d.get("ref") == ref), None)
        if existing:
            if existing["status"] == "issued":
                raise MxsatError("already_issued", f"ref {ref} was already invoiced ({existing['id']})")
            if existing["request"] == request and not replace:
                return existing, True
            if not replace:
                raise MxsatError("ref_conflict", f"ref {ref} already has a different pending draft "
                                 f"({existing['id']}); use --replace to redo it")
            if folio is None:
                folio = existing["comprobante"]["Folio"]
            store.delete_draft(existing["id"])

    amounts = amounts_for(template, subtotal=subtotal, total=total)
    number = int(folio) if folio is not None else next_folio(store, series)
    draft_id = f"{name}-{series}{number}"
    for d in store.drafts():
        if d["comprobante"].get("Serie", "") == series and d["comprobante"]["Folio"] == str(number):
            raise MxsatError("folio_taken", f"folio {series}{number} is already used by {d['id']}")

    s, t = amounts["subtotal"], amounts["total"]
    comprobante = {**template["comprobante"], "Folio": str(number), "Fecha": day.isoformat(),
                   "SubTotal": s2(s), "Total": s2(t)}
    concepto = {**template["concepto"],
                "Descripcion": render_description(template["concepto"].get("Descripcion", ""), per,
                                                  (pinfo or {}).get("lang", "es")),
                "ValorUnitario": s2(s), "Importe": s2(s)}
    impuestos = {}
    if any(x["TipoFactor"] != "Exento" for x in amounts["traslados"]):
        impuestos["TotalImpuestosTrasladados"] = s2(sum((dec(x["Importe"]) for x in amounts["traslados"]
                                                         if "Importe" in x), Decimal(0)))
    if amounts["retenciones"]:
        impuestos["TotalImpuestosRetenidos"] = s2(sum((dec(x["Importe"]) for x in amounts["retenciones"]),
                                                      Decimal(0)))
    problems = rule_problems(comprobante, template["receptor"], concepto, amounts["traslados"],
                             amounts["retenciones"])
    if problems:
        raise MxsatError("template_breaks_rules", "; ".join(problems))
    draft = {
        "id": draft_id,
        "template": name,
        "ref": ref,
        "status": "pending",
        "request": request,
        "period": request["period"],
        "comprobante": comprobante,
        "emisor": template["emisor"],
        "receptor": template["receptor"],
        "concepto": concepto,
        "traslados": amounts["traslados"],
        "retenciones": amounts["retenciones"],
        "cuenta_predial": template["cuenta_predial"],
        "impuestos": impuestos,
        "uuid": None,
        "verification": None,
    }
    return draft, False


def draft_personal(d: dict) -> list[str]:
    return [
        d["comprobante"].get("LugarExpedicion", ""), d["emisor"].get("Rfc", ""), d["emisor"].get("Nombre", ""),
        d["receptor"].get("Rfc", ""), d["receptor"].get("Nombre", ""),
        d["receptor"].get("DomicilioFiscalReceptor", ""), d["receptor"].get("NumRegIdTrib", ""),
        d["concepto"].get("Descripcion", ""), d["concepto"].get("NoIdentificacion", ""), *d["cuenta_predial"],
        d.get("uuid") or "",
    ]


def draft_view(d: dict, pz: Pseudonymizer, sheet: str | None = None) -> dict:
    comp, r = d["comprobante"], d["receptor"]
    view = {
        "id": d["id"],
        "template": d["template"],
        "ref": d.get("ref"),
        "status": d["status"],
        "date": comp["Fecha"],
        "period": d.get("period"),
        "series": comp.get("Serie"),
        "folio": comp["Folio"],
        "currency": comp.get("Moneda"),
        "subtotal": comp["SubTotal"],
        "transfers": [_tax_view(x) for x in d["traslados"]],
        "withholdings": [_tax_view(x) for x in d["retenciones"]],
        "total": comp["Total"],
        "total_cents": cents(dec(comp["Total"])),
        "payment_form": comp.get("FormaPago"),
        "payment_method": comp.get("MetodoPago"),
        "receiver_id": pz.party(r.get("Rfc"), r.get("Nombre"), r.get("NumRegIdTrib")),
        "cfdi_id": pz.id("cfdi", d["uuid"]) if d.get("uuid") else None,
    }
    if sheet:
        view["capture_sheet"] = sheet
    return view


def capture_sheet(d: dict) -> str:
    """The owner-facing sheet, in the order of the SAT portal. Contains personal data: it stays local."""
    comp, e, r, c = d["comprobante"], d["emisor"], d["receptor"], d["concepto"]

    def table(rows: list[tuple[str, str | None]]) -> str:
        lines = ["| Campo | Valor |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in rows if v]
        return "\n".join(lines)

    taxes = []
    for kind, rows in (("Traslado", d["traslados"]), ("Retención", d["retenciones"])):
        for t in rows:
            rate = "" if t["TipoFactor"] == "Exento" else t.get("TasaOCuota", "")
            taxes.append(f"| {kind} | {cat.IMPUESTO.get(t['Impuesto'], t['Impuesto'])} | {t['TipoFactor']} | "
                         f"{rate} | {t['Base']} | {t.get('Importe', '—')} |")
    tax_table = "\n".join(["| Tipo | Impuesto | Factor | Tasa | Base | Importe |", "|---|---|---|---|---|---|", *taxes])
    totals = [("Subtotal", comp["SubTotal"])]
    if "TotalImpuestosTrasladados" in d["impuestos"]:
        totals.append(("Impuestos trasladados", d["impuestos"]["TotalImpuestosTrasladados"]))
    if "TotalImpuestosRetenidos" in d["impuestos"]:
        totals.append(("Impuestos retenidos", d["impuestos"]["TotalImpuestosRetenidos"]))
    totals.append(("**Total**", f"**{comp['Total']}**"))
    return f"""# Factura por capturar · {d['id']}

Plantilla `{d['template']}`{f" · referencia `{d['ref']}`" if d.get('ref') else ''}{f" · periodo {d['period']}" if d.get('period') else ''}

Captura estos datos en el portal de factura electrónica del SAT. Al terminar, guarda el XML timbrado y
entrégaselo al agente para verificarlo contra esta ficha.

## Comprobante

{table([
    ("Tipo de comprobante", cat.label(cat.TIPO_COMPROBANTE, comp.get('TipoDeComprobante'))),
    ("Serie", comp.get('Serie')), ("Folio", comp['Folio']), ("Fecha", comp['Fecha']),
    ("Lugar de expedición (CP)", comp.get('LugarExpedicion')), ("Moneda", comp.get('Moneda')),
    ("Forma de pago", cat.label(cat.FORMA_PAGO, comp.get('FormaPago'))),
    ("Método de pago", cat.label(cat.METODO_PAGO, comp.get('MetodoPago'))),
    ("Exportación", cat.label(cat.EXPORTACION, comp.get('Exportacion'))),
])}

## Emisor

{table([("RFC", e.get('Rfc')), ("Nombre", e.get('Nombre')),
        ("Régimen fiscal", cat.label(cat.REGIMEN_FISCAL, e.get('RegimenFiscal')))])}

## Receptor

{table([
    ("RFC", r.get('Rfc')), ("Nombre", r.get('Nombre')),
    ("Domicilio fiscal (CP)", r.get('DomicilioFiscalReceptor')),
    ("Residencia fiscal", r.get('ResidenciaFiscal')), ("Número de registro de identidad fiscal", r.get('NumRegIdTrib')),
    ("Régimen fiscal", cat.label(cat.REGIMEN_FISCAL, r.get('RegimenFiscalReceptor'))),
    ("Uso del CFDI", cat.label(cat.USO_CFDI, r.get('UsoCFDI'))),
])}

## Concepto

{table([
    ("Clave de producto o servicio", c.get('ClaveProdServ')), ("No. de identificación", c.get('NoIdentificacion')),
    ("Cantidad", c.get('Cantidad')), ("Clave de unidad", c.get('ClaveUnidad')), ("Unidad", c.get('Unidad')),
    ("Descripción", c.get('Descripcion')), ("Valor unitario", c['ValorUnitario']), ("Importe", c['Importe']),
    ("Objeto de impuesto", cat.label(cat.OBJETO_IMP, c.get('ObjetoImp'))),
    ("Cuenta predial", ", ".join(d['cuenta_predial'])),
])}

### Impuestos del concepto

{tax_table}

## Totales

{table(totals)}
"""


def discard_draft(store: Store, draft_id: str) -> dict:
    d = store.load_draft(draft_id)
    if d["status"] == "issued":
        raise MxsatError("already_issued", "an issued draft cannot be discarded")
    store.delete_draft(draft_id)
    return d


# -- verification ----------------------------------------------------------------------------------------

def _same(kind: str, a: str | None, b: str | None) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    if kind == "num":
        return dec(a) == dec(b)
    return norm(a) == norm(b)


def verify(store: Store, raw: dict, draft_id: str, accept: bool = False) -> dict:
    d = store.load_draft(draft_id)
    if not raw["tfd"]:
        raise MxsatError("not_stamped", "the XML has no TimbreFiscalDigital; give the stamped invoice")
    uuid = raw["tfd"]["UUID"].upper()
    if d["status"] == "issued":
        if d["uuid"] == uuid:
            return {"draft": d, "matches": d["verification"]["matches"], "failed": d["verification"]["failed"],
                    "warnings": d["verification"]["warnings"], "passed": d["verification"]["passed"],
                    "unchanged": True}
        raise MxsatError("already_issued", "this draft was already verified against another invoice")
    other = next((x for x in store.drafts() if x.get("uuid") == uuid), None)
    if other:
        raise MxsatError("uuid_already_linked", f"this invoice is already linked to {other['id']}")

    failed: list[dict] = []
    warnings: list[dict] = []
    passed = 0

    def check(field: str, expected, found, kind: str = "text", sensitive: bool = False, severity: str = "error"):
        nonlocal passed
        if _same(kind, expected, found):
            passed += 1
            return
        item = {"field": field, "severity": severity}
        if sensitive:
            item["detail"] = "differs (personal value, not shown)"
        else:
            item["expected"], item["found"] = expected, found
        (failed if severity == "error" else warnings).append(item)

    comp, x = d["comprobante"], raw["comprobante"]
    check("Version", "4.0", raw["version"])
    for key in ("TipoDeComprobante", "Serie", "Folio", "Moneda", "FormaPago", "MetodoPago", "Exportacion"):
        check(key, comp.get(key), x.get(key))
    check("LugarExpedicion", comp.get("LugarExpedicion"), x.get("LugarExpedicion"), sensitive=True)
    check("TipoCambio", None, x.get("TipoCambio"), "num")
    check("SubTotal", comp["SubTotal"], x.get("SubTotal"), "num")
    check("Descuento", None, x.get("Descuento"), "num")
    check("Total", comp["Total"], x.get("Total"), "num")
    check("Fecha", comp["Fecha"], (x.get("Fecha") or "")[:10], severity="warning")
    for key in ("Rfc", "Nombre"):
        check(f"Emisor.{key}", d["emisor"].get(key), raw["emisor"].get(key), sensitive=True)
    check("Emisor.RegimenFiscal", d["emisor"].get("RegimenFiscal"), raw["emisor"].get("RegimenFiscal"))
    for key in ("Rfc", "Nombre", "DomicilioFiscalReceptor", "NumRegIdTrib"):
        check(f"Receptor.{key}", d["receptor"].get(key), raw["receptor"].get(key), sensitive=True)
    for key in ("RegimenFiscalReceptor", "UsoCFDI", "ResidenciaFiscal"):
        check(f"Receptor.{key}", d["receptor"].get(key), raw["receptor"].get(key))

    if len(raw["conceptos"]) != 1:
        failed.append({"field": "Conceptos", "severity": "error", "expected": "1", "found": str(len(raw["conceptos"]))})
    else:
        rc = raw["conceptos"][0]
        a, c = rc["attrs"], d["concepto"]
        for key in ("ClaveProdServ", "ClaveUnidad", "ObjetoImp"):
            check(f"Concepto.{key}", c.get(key), a.get(key))
        check("Concepto.Unidad", c.get("Unidad"), a.get("Unidad"), severity="warning")
        for key in ("Cantidad", "ValorUnitario", "Importe"):
            check(f"Concepto.{key}", c.get(key), a.get(key), "num")
        check("Concepto.Descuento", None, a.get("Descuento"), "num")
        for key in ("Descripcion", "NoIdentificacion"):
            check(f"Concepto.{key}", c.get(key), a.get(key), sensitive=True)
        check("Concepto.CuentaPredial", "|".join(d["cuenta_predial"]), "|".join(rc["cuenta_predial"]), sensitive=True)
        for kind, mine, theirs in (("Traslado", d["traslados"], rc["impuestos"]["traslados"]),
                                   ("Retencion", d["retenciones"], rc["impuestos"]["retenciones"])):
            if len(mine) != len(theirs):
                failed.append({"field": f"Concepto.{kind}s", "severity": "error",
                               "expected": str(len(mine)), "found": str(len(theirs))})
                continue
            for i, (m, t) in enumerate(zip(mine, theirs, strict=False)):
                for key in ("Impuesto", "TipoFactor"):
                    check(f"Concepto.{kind}[{i}].{key}", m.get(key), t.get(key))
                for key in ("TasaOCuota", "Base", "Importe"):
                    check(f"Concepto.{kind}[{i}].{key}", m.get(key), t.get(key), "num")
    for key in ("TotalImpuestosTrasladados", "TotalImpuestosRetenidos"):
        check(f"Impuestos.{key}", d["impuestos"].get(key), raw["impuestos"]["attrs"].get(key), "num")

    matches = not failed
    d["verification"] = {"matches": matches, "failed": failed, "warnings": warnings, "passed": passed,
                         "accepted_with_differences": bool(failed and accept)}
    if matches or accept:
        d["status"] = "issued"
        d["uuid"] = uuid
        d["stamped_at"] = raw["tfd"].get("FechaTimbrado")
        store.record_folio(x.get("Serie", ""), x.get("Folio"))
    store.save_draft(d, capture_sheet(d))
    return {"draft": d, "matches": matches, "failed": failed, "warnings": warnings, "passed": passed,
            "unchanged": False}
