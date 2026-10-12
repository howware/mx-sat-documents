"""Read a CFDI (3.3 or 4.0) into a raw structure that keeps the SAT's attribute names.

The raw structure holds personal data and never leaves this process except through ``public_view`` (which
replaces personal values with pseudonyms) or the private store.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import MxsatError
from .money import cents, dec, money_out
from .privacy import GENERIC_RFCS, Pseudonymizer, norm, rfc_kind

NS = {"4.0": "http://www.sat.gob.mx/cfd/4", "3.3": "http://www.sat.gob.mx/cfd/3"}
TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"
DROP = {"Sello", "Certificado", "NoCertificado", "SelloCFD", "SelloSAT"}


def _attrs(el: ET.Element | None) -> dict[str, str]:
    if el is None:
        return {}
    return {k: v for k, v in el.attrib.items() if not k.startswith("{") and k not in DROP}


def load(path: str | Path) -> dict:
    try:
        data = Path(path).read_bytes()
    except OSError:
        raise MxsatError("file_not_readable", "cannot read the file") from None
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise MxsatError("not_a_cfdi", "XML with a DOCTYPE or entities is not accepted")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise MxsatError("not_a_cfdi", f"the file is not well-formed XML ({e.position[0]}:{e.position[1]})") from None
    return parse(root)


def parse(root: ET.Element) -> dict:
    ns = next((u for u in NS.values() if root.tag == f"{{{u}}}Comprobante"), None)
    if ns is None:
        raise MxsatError("not_a_cfdi", "the file is not a CFDI (no cfdi:Comprobante root)")

    def q(name: str) -> str:
        return f"{{{ns}}}{name}"

    def taxes(parent: ET.Element | None) -> dict:
        if parent is None:
            return {"attrs": {}, "traslados": [], "retenciones": [], "present": False}
        return {
            "attrs": _attrs(parent),
            "traslados": [_attrs(t) for t in parent.iterfind(f"{q('Traslados')}/{q('Traslado')}")],
            "retenciones": [_attrs(t) for t in parent.iterfind(f"{q('Retenciones')}/{q('Retencion')}")],
            "present": True,
        }

    conceptos = []
    for c in root.iterfind(f"{q('Conceptos')}/{q('Concepto')}"):
        conceptos.append({
            "attrs": _attrs(c),
            "impuestos": taxes(c.find(q("Impuestos"))),
            "cuenta_predial": [_attrs(p).get("Numero", "") for p in c.findall(q("CuentaPredial"))],
            "terceros": _attrs(c.find(q("ACuentaTerceros"))),
            "partes": len(c.findall(q("Parte"))),
            "aduana": len(c.findall(q("InformacionAduanera"))),
        })

    complementos, tfd = [], {}
    comp = root.find(q("Complemento"))
    if comp is not None:
        for child in comp:
            complementos.append(child.tag.split("}")[-1])
            if child.tag == f"{{{TFD_NS}}}TimbreFiscalDigital":
                tfd = _attrs(child)

    relacionados = []
    for group in root.findall(q("CfdiRelacionados")):
        relacionados.append({
            "TipoRelacion": group.get("TipoRelacion", ""),
            "uuids": [r.get("UUID", "") for r in group.findall(q("CfdiRelacionado"))],
        })

    comprobante = _attrs(root)
    return {
        "version": comprobante.get("Version", ""),
        "comprobante": comprobante,
        "informacion_global": _attrs(root.find(q("InformacionGlobal"))),
        "relacionados": relacionados,
        "emisor": _attrs(root.find(q("Emisor"))),
        "receptor": _attrs(root.find(q("Receptor"))),
        "conceptos": conceptos,
        "impuestos": taxes(root.find(q("Impuestos"))),
        "complementos": complementos,
        "tfd": tfd,
    }


def personal_values(raw: dict) -> list[str]:
    """Every value in the document that identifies or locates a person."""
    out = [
        raw["comprobante"].get("LugarExpedicion", ""),
        raw["emisor"].get("Rfc", ""), raw["emisor"].get("Nombre", ""),
        raw["receptor"].get("Rfc", ""), raw["receptor"].get("Nombre", ""),
        raw["receptor"].get("DomicilioFiscalReceptor", ""), raw["receptor"].get("NumRegIdTrib", ""),
        raw["tfd"].get("UUID", ""),
    ]
    for c in raw["conceptos"]:
        out += [c["attrs"].get("Descripcion", ""), c["attrs"].get("NoIdentificacion", "")]
        out += c["cuenta_predial"]
        out += list(c["terceros"].values())
    for group in raw["relacionados"]:
        out += group["uuids"]
    return [v for v in out if v and norm(v) not in GENERIC_RFCS]


def _tax_out(t: dict) -> dict:
    return {
        "tax": {"001": "ISR", "002": "IVA", "003": "IEPS"}.get(t.get("Impuesto", ""), t.get("Impuesto")),
        "factor": t.get("TipoFactor"),
        "rate": t.get("TasaOCuota"),
        "base": money_out(t.get("Base")),
        "amount": money_out(t.get("Importe")),
    }


def document_id(pz: Pseudonymizer, uuid: str | None) -> str | None:
    return pz.id("cfdi", uuid.upper()) if uuid else None


def public_view(raw: dict, pz: Pseudonymizer) -> dict:
    comp, emisor, receptor, tfd = raw["comprobante"], raw["emisor"], raw["receptor"], raw["tfd"]
    concepts = []
    for c in raw["conceptos"]:
        a = c["attrs"]
        concepts.append({
            "product_code": a.get("ClaveProdServ"),
            "unit_code": a.get("ClaveUnidad"),
            "unit": a.get("Unidad"),
            "quantity": a.get("Cantidad"),
            "unit_value": money_out(a.get("ValorUnitario")),
            "amount": money_out(a.get("Importe")),
            "discount": money_out(a.get("Descuento")),
            "tax_object": a.get("ObjetoImp"),
            "description_id": pz.id("text", a.get("Descripcion")) if a.get("Descripcion") else None,
            "identification": "present" if a.get("NoIdentificacion") else None,
            "property_tax_accounts": len(c["cuenta_predial"]),
            "third_party": bool(c["terceros"]),
            "parts": c["partes"],
            "transfers": [_tax_out(t) for t in c["impuestos"]["traslados"]],
            "withholdings": [_tax_out(t) for t in c["impuestos"]["retenciones"]],
        })
    taxes = raw["impuestos"]["attrs"]
    total = comp.get("Total")
    return {
        "id": document_id(pz, tfd.get("UUID")),
        "kind": "cfdi",
        "version": raw["version"],
        "type": comp.get("TipoDeComprobante"),
        "series": comp.get("Serie"),
        "folio": comp.get("Folio"),
        "issued_at": comp.get("Fecha"),
        "stamped": bool(tfd),
        "stamped_at": tfd.get("FechaTimbrado"),
        "stamped_by_sat": tfd.get("RfcProvCertif") == "SAT970701NN3" if tfd else None,
        "currency": comp.get("Moneda"),
        "exchange_rate": comp.get("TipoCambio"),
        "subtotal": money_out(comp.get("SubTotal")),
        "discount": money_out(comp.get("Descuento")),
        "total": money_out(total),
        "total_cents": cents(dec(total)) if total else None,
        "payment_form": comp.get("FormaPago"),
        "payment_method": comp.get("MetodoPago"),
        "export": comp.get("Exportacion"),
        "place_of_issue_id": pz.id("place", comp.get("LugarExpedicion")) if comp.get("LugarExpedicion") else None,
        "global_information": raw["informacion_global"] or None,
        "issuer": {
            "id": pz.party(emisor.get("Rfc")),
            "rfc_kind": rfc_kind(emisor.get("Rfc")),
            "regime": emisor.get("RegimenFiscal"),
        },
        "receiver": {
            "id": pz.party(receptor.get("Rfc"), receptor.get("Nombre"), receptor.get("NumRegIdTrib")),
            "rfc_kind": rfc_kind(receptor.get("Rfc")),
            "regime": receptor.get("RegimenFiscalReceptor"),
            "use": receptor.get("UsoCFDI"),
            "tax_residence": receptor.get("ResidenciaFiscal"),
            "foreign_tax_id": "present" if receptor.get("NumRegIdTrib") else None,
            "postal_code_id": pz.id("place", receptor.get("DomicilioFiscalReceptor"))
            if receptor.get("DomicilioFiscalReceptor") else None,
        },
        "concepts": concepts,
        "taxes": {
            "transferred_total": money_out(taxes.get("TotalImpuestosTrasladados")),
            "withheld_total": money_out(taxes.get("TotalImpuestosRetenidos")),
        },
        "related": [
            {"relation": g["TipoRelacion"], "ids": [document_id(pz, u) for u in g["uuids"]]}
            for g in raw["relacionados"]
        ],
        "complements": raw["complementos"],
    }
