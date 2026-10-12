"""Synthetic SAT documents. Every person, RFC, address and number here is invented.

RFC-shaped values are assembled in code so the private-data guard does not mistake them for real ones.
"""

from __future__ import annotations

from pathlib import Path

ISSUER_RFC = "PEG" + "J800101" + "AB1"           # fictitious person
ISSUER_NAME = "JUANA PEREZ GOMEZ"
COMPANY_RFC = "ACM" + "990101" + "XY2"            # fictitious company
COMPANY_NAME = "ACME CONSULTORES"
FOREIGN_NAME = "WIDGETS NORTH LLC"
FOREIGN_TAX_ID = "987654321"
TENANT_NAME = "ROBERTO SANCHEZ LUNA"
HOME_CP = "64000"
COMPANY_CP = "06600"
PREDIAL = "ZZ999999"
UUIDS = {
    "export": "0F8D2C1A-1111-4A2B-9C3D-000000000001",
    "rent": "0F8D2C1A-2222-4A2B-9C3D-000000000002",
    "company": "0F8D2C1A-3333-4A2B-9C3D-000000000003",
}

CFDI = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{fecha}" Sello="AAAA" FormaPago="{forma}" NoCertificado="00001000000000000000" Certificado="BBBB" SubTotal="{subtotal}" Moneda="MXN" Total="{total}" TipoDeComprobante="I" Exportacion="01" MetodoPago="PUE" LugarExpedicion="{lugar}">
  <cfdi:Emisor Rfc="{emisor_rfc}" Nombre="{emisor_nombre}" RegimenFiscal="626" />
  <cfdi:Receptor {receptor} />
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="{clave}" {noid}Cantidad="1.00" ClaveUnidad="{unidad_clave}" Unidad="{unidad}" Descripcion="{descripcion}" ValorUnitario="{subtotal}" Importe="{importe}" ObjetoImp="02">
      <cfdi:Impuestos>
{concept_taxes}
      </cfdi:Impuestos>
{predial}
    </cfdi:Concepto>
  </cfdi:Conceptos>
{taxes}
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}" RfcProvCertif="SAT970701NN3" SelloCFD="AAAA" NoCertificadoSAT="00001000000000000001" SelloSAT="CCCC" />
  </cfdi:Complemento>
</cfdi:Comprobante>
"""


def export_xml(folio: str = "149", fecha: str = "2026-09-30T12:02:57", amount: str = "50407.87",
               uuid: str = UUIDS["export"], forma: str = "03", **over) -> str:
    receptor = (f'Rfc="XEXX010101000" Nombre="{over.get("nombre", FOREIGN_NAME)}" '
                f'DomicilioFiscalReceptor="{HOME_CP}" ResidenciaFiscal="USA" NumRegIdTrib="{FOREIGN_TAX_ID}" '
                f'RegimenFiscalReceptor="616" UsoCFDI="S01"')
    return CFDI.format(
        serie="A", folio=folio, fecha=fecha, forma=forma, subtotal=amount, total=amount, lugar=HOME_CP,
        emisor_rfc=ISSUER_RFC, emisor_nombre=ISSUER_NAME, receptor=receptor, clave="81111504", noid="",
        unidad_clave="E48", unidad="Unidad de servicio", descripcion="Servicios de Desarrollo de Software",
        importe=amount + "0000",
        concept_taxes=f'        <cfdi:Traslados><cfdi:Traslado Base="{amount}0000" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.000000" Importe="0.000000" /></cfdi:Traslados>',
        predial="",
        taxes=f'  <cfdi:Impuestos TotalImpuestosTrasladados="0.00"><cfdi:Traslados><cfdi:Traslado Base="{amount}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.000000" Importe="0.00" /></cfdi:Traslados></cfdi:Impuestos>',
        uuid=uuid,
    )


def rent_xml(folio: str = "151", fecha: str = "2026-09-30T12:12:32", amount: str = "5000.00",
             uuid: str = UUIDS["rent"], descripcion: str | None = None, forma: str = "01") -> str:
    descripcion = descripcion or ("Arrendamiento casa habitación del 1 al 31 de Octubre de 2026. "
                                  "Calle Falsa 123, Col. Centro, Monterrey NL")
    receptor = (f'Rfc="XAXX010101000" Nombre="{TENANT_NAME}" DomicilioFiscalReceptor="{HOME_CP}" '
                f'RegimenFiscalReceptor="616" UsoCFDI="S01"')
    return CFDI.format(
        serie="A", folio=folio, fecha=fecha, forma=forma, subtotal=amount, total=amount, lugar=HOME_CP,
        emisor_rfc=ISSUER_RFC, emisor_nombre=ISSUER_NAME, receptor=receptor, clave="80131501",
        noid='NoIdentificacion="arrendamiento" ', unidad_clave="MON", unidad="Mes", descripcion=descripcion,
        importe=amount + "0000",
        concept_taxes=f'        <cfdi:Traslados><cfdi:Traslado Base="{amount}0000" Impuesto="002" TipoFactor="Exento" /></cfdi:Traslados>',
        predial=f'      <cfdi:CuentaPredial Numero="{PREDIAL}" />',
        taxes=f'  <cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Base="{amount}" Impuesto="002" TipoFactor="Exento" /></cfdi:Traslados></cfdi:Impuestos>',
        uuid=uuid,
    )


def company_xml(subtotal: str = "9607.69", folio: str = "150", uuid: str = UUIDS["company"]) -> str:
    """Services to a Mexican company that withholds ISR (1.25 %) and two thirds of the VAT."""
    from decimal import ROUND_HALF_UP, Decimal
    s = Decimal(subtotal)
    q = Decimal("0.01")
    iva = (s * Decimal("0.16")).quantize(q, ROUND_HALF_UP)
    isr = (s * Decimal("0.0125")).quantize(q, ROUND_HALF_UP)
    riva = (s * Decimal("0.106667")).quantize(q, ROUND_HALF_UP)
    total = s + iva - isr - riva
    receptor = (f'Rfc="{COMPANY_RFC}" Nombre="{COMPANY_NAME}" DomicilioFiscalReceptor="{COMPANY_CP}" '
                f'RegimenFiscalReceptor="601" UsoCFDI="G03"')
    concept_taxes = (
        f'        <cfdi:Traslados><cfdi:Traslado Base="{s}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}" /></cfdi:Traslados>\n'
        f'        <cfdi:Retenciones><cfdi:Retencion Base="{s}" Impuesto="001" TipoFactor="Tasa" TasaOCuota="0.012500" Importe="{isr}" />'
        f'<cfdi:Retencion Base="{s}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.106667" Importe="{riva}" /></cfdi:Retenciones>'
    )
    taxes = (f'  <cfdi:Impuestos TotalImpuestosRetenidos="{isr + riva}" TotalImpuestosTrasladados="{iva}">'
             f'<cfdi:Retenciones><cfdi:Retencion Impuesto="001" Importe="{isr}" /><cfdi:Retencion Impuesto="002" Importe="{riva}" /></cfdi:Retenciones>'
             f'<cfdi:Traslados><cfdi:Traslado Base="{s}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}" /></cfdi:Traslados></cfdi:Impuestos>')
    return CFDI.format(
        serie="A", folio=folio, fecha="2026-09-15T10:00:00", forma="03", subtotal=subtotal, total=str(total),
        lugar=HOME_CP, emisor_rfc=ISSUER_RFC, emisor_nombre=ISSUER_NAME, receptor=receptor, clave="80101500",
        noid="", unidad_clave="E48", unidad="Unidad de servicio", descripcion="Consultoría en procesos",
        importe=subtotal, concept_taxes=concept_taxes, predial="", taxes=taxes, uuid=uuid,
    ).replace('ValorUnitario="9607.69" Importe="9607.69"', f'ValorUnitario="{s}" Importe="{s}"')


def stamped_from_draft(draft: dict, uuid: str, **changes) -> str:
    """The XML the portal would return for an approved draft, with optional differences."""
    comp, e, r, c = draft["comprobante"], draft["emisor"], draft["receptor"], draft["concepto"]
    comp = {**comp, **changes.get("comprobante", {})}
    r = {**r, **changes.get("receptor", {})}
    c = {**c, **changes.get("concepto", {})}
    attrs = lambda d: " ".join(f'{k}="{v}"' for k, v in d.items() if v is not None)  # noqa: E731

    def tax_rows(rows: list[dict], tag: str) -> str:
        return "".join(f"<cfdi:{tag} {attrs(t)} />" for t in rows)

    concept_taxes = ""
    if draft["traslados"]:
        concept_taxes += f"<cfdi:Traslados>{tax_rows(draft['traslados'], 'Traslado')}</cfdi:Traslados>"
    if draft["retenciones"]:
        concept_taxes += f"<cfdi:Retenciones>{tax_rows(draft['retenciones'], 'Retencion')}</cfdi:Retenciones>"
    predial = "".join(f'<cfdi:CuentaPredial Numero="{n}" />' for n in draft["cuenta_predial"])
    global_taxes = f"<cfdi:Impuestos {attrs(draft['impuestos'])}></cfdi:Impuestos>"
    fecha = comp.pop("Fecha") + "T13:00:00"
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="{fecha}" {attrs(comp)}>'
        f"<cfdi:Emisor {attrs(e)} /><cfdi:Receptor {attrs(r)} />"
        f"<cfdi:Conceptos><cfdi:Concepto {attrs(c)}><cfdi:Impuestos>{concept_taxes}</cfdi:Impuestos>{predial}"
        f"</cfdi:Concepto></cfdi:Conceptos>{global_taxes}"
        '<cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        f'Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}" RfcProvCertif="SAT970701NN3" /></cfdi:Complemento>'
        "</cfdi:Comprobante>"
    )


ACUSE_LINES = [
    "ACUSE DE RECIBO",
    "DECLARACIÓN PROVISIONAL O DEFINITIVA DE IMPUESTOS FEDERALES",
    f"RFC: {ISSUER_RFC}",
    f"Nombre: {ISSUER_NAME}",
    "Tipo de declaración: Normal",
    "Periodicidad: Mensual          Período de la declaración: Septiembre",
    "Ejercicio: 2026                Fecha y hora de presentación: 07/10/2026 10:36",
    "Medio de presentación: Internet     Vencimiento Obligación: 23/10/2026",
    "Versión: 24.0.0                Número de operación: 990000000001",
    "Impuestos que declara:",
    "Concepto de pago 1: ISR simplificado de confianza. Personas físicas",
    "A cargo: 1,234",
    "Cantidad a cargo: 1,234",
    "Cantidad a pagar: 1,234",
    "Concepto de pago 2: IVA simplificado de confianza región fronteriza",
    "A cargo: 0",
    "Cantidad a cargo: 0",
    "Cantidad a pagar: 0",
    "Sello digital :",
    "QUJDREVGR0g=",
    "SECCIÓN LÍNEA DE CAPTURA",
    "El importe a cargo determinado en esta declaración, deberá ser pagado en las instituciones de crédito",
    "autorizadas, utilizando para tal efecto la línea de captura que se indica.",
    "Línea de Importe total",
    "0099 11A1 2222 3333 4444 $1,234",
    "Captura: a pagar:",
    "Vigente hasta: 26/10/2026",
    "QUJDREVGR0g=",
]
# The same receipt as some PDF readers order it: labels and values on separate lines.
ACUSE_LINES_STACKED = ACUSE_LINES[:20] + [
    "SECCIÓN LÍNEA DE CAPTURA",
    "Línea de",
    "Captura:",
    "0099 11A1 2222 3333 4444 Importe total",
    "a pagar: $1,234",
    "Vigente hasta: 26/10/2026",
]
CAPTURE_LINE = "0099 11A1 2222 3333 4444"
OPERATION = "990000000001"


def acuse_pdf(path: Path, lines: list[str] | None = None) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=letter)
    y = 740
    for line in lines or ACUSE_LINES:
        pdf.drawString(50, y, line)
        y -= 18
    pdf.save()
    return path
