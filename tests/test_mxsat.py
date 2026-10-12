from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest

from mxsat import cfdi, invoices
from mxsat.cli import main
from mxsat.errors import MxsatError
from mxsat.privacy import Pseudonymizer, find_leaks
from mxsat.store import Store

from . import synthetic as syn

PERSONAL = [syn.ISSUER_RFC, syn.ISSUER_NAME, syn.COMPANY_RFC, syn.COMPANY_NAME, syn.FOREIGN_NAME,
            syn.FOREIGN_TAX_ID, syn.TENANT_NAME, syn.HOME_CP, syn.COMPANY_CP, syn.PREDIAL, *syn.UUIDS.values(),
            "Calle Falsa", syn.CAPTURE_LINE, syn.OPERATION]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MXSAT_KEY", "test-key-not-secret")
    monkeypatch.setenv("MXSAT_STORE", str(tmp_path / "store"))
    files = {}
    for name, xml in (("export", syn.export_xml()), ("rent", syn.rent_xml()), ("company", syn.company_xml())):
        files[name] = tmp_path / f"{name}.xml"
        files[name].write_text(xml, encoding="utf-8")
    return tmp_path, files


def run(capsys, *argv) -> tuple[int, dict, str]:
    code = main(list(argv))
    out = capsys.readouterr()
    return code, json.loads(out.out), out.out


def assert_no_personal(text: str):
    for value in PERSONAL:
        assert value.upper() not in text.upper(), "personal value leaked"
    assert not find_leaks(text, [])


# -- read ------------------------------------------------------------------------------------------------

def test_read_hides_personal_data_and_keeps_the_numbers(env, capsys):
    _, files = env
    code, out, text = run(capsys, "cfdi", "read", str(files["export"]), str(files["rent"]), str(files["company"]))
    assert code == 0
    assert_no_personal(text)
    export, rent, company = out["documents"]
    assert export["total"] == "50407.87" and export["total_cents"] == 5040787
    assert export["receiver"]["rfc_kind"] == "generic_foreign" and export["receiver"]["tax_residence"] == "USA"
    assert export["concepts"][0]["transfers"] == [
        {"tax": "IVA", "factor": "Tasa", "rate": "0.000000", "base": "50407.87", "amount": "0.00"}]
    assert export["stamped_by_sat"] is True and export["payment_form"] == "03"
    assert rent["receiver"]["rfc_kind"] == "generic_public"
    assert rent["concepts"][0]["transfers"][0]["factor"] == "Exento"
    assert rent["concepts"][0]["property_tax_accounts"] == 1
    assert company["receiver"]["rfc_kind"] == "company"
    assert company["taxes"]["withheld_total"] == "1144.92"
    # the same issuer gets the same id in every document
    assert export["issuer"]["id"] == rent["issuer"]["id"] == company["issuer"]["id"]


def test_ids_are_stable_with_a_key_and_differ_between_keys(env, capsys, monkeypatch):
    _, files = env
    a = run(capsys, "cfdi", "read", str(files["export"]))[1]["documents"][0]["id"]
    b = run(capsys, "cfdi", "read", str(files["export"]))[1]["documents"][0]["id"]
    monkeypatch.setenv("MXSAT_KEY", "another-key")
    c = run(capsys, "cfdi", "read", str(files["export"]))[1]["documents"][0]["id"]
    assert a == b != c


def test_generic_rfc_parties_are_told_apart_by_name():
    pz = Pseudonymizer(b"k")
    assert pz.party("XAXX010101000", "ANA") != pz.party("XAXX010101000", "LUIS")


def test_rejects_doctype_and_non_cfdi(tmp_path, capsys):
    bomb = tmp_path / "bomb.xml"
    bomb.write_text('<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>', encoding="utf-8")
    other = tmp_path / "other.xml"
    other.write_text("<root/>", encoding="utf-8")
    assert run(capsys, "cfdi", "read", str(bomb))[1]["error"]["code"] == "not_a_cfdi"
    code, out, _ = run(capsys, "cfdi", "read", str(other))
    assert code == 2 and out["error"]["code"] == "not_a_cfdi"


def test_privacy_check_fails_closed(monkeypatch, env, capsys):
    _, files = env
    real = cfdi.public_view
    monkeypatch.setattr(cfdi, "public_view", lambda raw, pz: {**real(raw, pz), "oops": raw["receptor"]["Nombre"]})
    code, out, text = run(capsys, "cfdi", "read", str(files["export"]))
    assert code == 4 and out["error"]["code"] == "privacy_check_failed"
    assert syn.FOREIGN_NAME not in text


# -- templates and periods -------------------------------------------------------------------------------

def test_period_placeholders_are_learned_from_the_description():
    text, info = invoices.detect_period("Arrendamiento del 1 al 31 de Octubre de 2026. Calle X",
                                        dt.date(2026, 9, 30))
    assert text == "Arrendamiento del {first_day} al {last_day} de {Month} de {year}. Calle X"
    assert info == {"lang": "es", "offset_months": 1, "placeholders": ["day_range", "month", "year"]}
    assert invoices.render_description(text, (2027, 2), "es") == "Arrendamiento del 1 al 28 de Febrero de 2027. Calle X"
    assert invoices.render_description(text, (2028, 2), "es").startswith("Arrendamiento del 1 al 29 de Febrero de 2028")
    assert invoices.detect_period("Servicios de Desarrollo de Software", dt.date(2026, 9, 30)) == (
        "Servicios de Desarrollo de Software", None)
    # a day range that is not the whole month is left alone
    text, _ = invoices.detect_period("Renta del 1 al 15 de octubre", dt.date(2026, 10, 1))
    assert text == "Renta del 1 al 15 de {month}"


def test_template_is_private_and_reported_with_pseudonyms(env, capsys):
    tmp, files = env
    code, out, text = run(capsys, "cfdi", "template", str(files["rent"]), "--name", "rent")
    assert code == 0
    assert_no_personal(text)
    t = out["template"]
    assert t["period"]["offset_months"] == 1 and t["warnings"] == []
    assert t["payment_form"] == "01" and t["transfers"] == [{"tax": "IVA", "factor": "Exento", "rate": None}]
    stored = (tmp / "store" / "templates" / "rent.json").read_text(encoding="utf-8")
    assert syn.TENANT_NAME in stored and syn.PREDIAL in stored
    assert (tmp / "store" / ".gitignore").read_text() == "*\n"
    assert run(capsys, "cfdi", "template", str(files["rent"]), "--name", "rent")[1]["error"]["code"] == "template_exists"


# -- drafts ----------------------------------------------------------------------------------------------

def test_rent_draft_fills_the_next_month_and_the_next_folio(env, capsys):
    tmp, files = env
    run(capsys, "cfdi", "template", str(files["export"]), "--name", "export")
    run(capsys, "cfdi", "template", str(files["rent"]), "--name", "rent")
    code, out, text = run(capsys, "cfdi", "draft", "--template", "rent", "--total", "5000", "--date", "2026-10-30",
                          "--ref", "tx_rent_oct")
    assert code == 0
    assert_no_personal(text)
    d = out["draft"]
    assert d["id"] == "rent-A152" and d["period"] == "2026-11" and d["total"] == "5000.00"
    sheet = (tmp / "store" / "drafts" / "rent-A152.md").read_text(encoding="utf-8")
    assert "del 1 al 30 de Noviembre de 2026" in sheet
    assert syn.TENANT_NAME in sheet and syn.PREDIAL in sheet and "01 (Efectivo)" in sheet
    out2 = run(capsys, "cfdi", "draft", "--template", "export", "--total", "61,250.10", "--date", "2026-10-30")[1]
    assert out2["draft"]["id"] == "export-A153" and out2["draft"]["subtotal"] == "61250.10"


def test_gross_up_from_the_deposit_is_exact(env, capsys):
    _, files = env
    run(capsys, "cfdi", "template", str(files["company"]), "--name", "acme")
    d = run(capsys, "cfdi", "draft", "--template", "acme", "--total", "10000.00", "--date", "2026-10-15")[1]["draft"]
    assert d["subtotal"] == "9607.69" and d["total"] == "10000.00"
    assert [x["amount"] for x in d["transfers"]] == ["1537.23"]
    assert [x["amount"] for x in d["withholdings"]] == ["120.10", "1024.82"]


def test_gross_up_always_lands_on_the_total_or_says_so():
    template = {"traslados": [{"Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.160000"}],
                "retenciones": [{"Impuesto": "001", "TipoFactor": "Tasa", "TasaOCuota": "0.012500"},
                                {"Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.106667"}]}
    impossible = 0
    for c in range(1_000_000, 1_000_400):
        total = Decimal(c) / 100
        try:
            a = invoices.amounts_for(template, total=str(total))
            assert a["total"] == total
        except MxsatError as e:
            assert e.code == "no_exact_subtotal"
            impossible += 1
    assert impossible < 100


def test_a_deposit_is_never_invoiced_twice(env, capsys):
    tmp, files = env
    run(capsys, "cfdi", "template", str(files["export"]), "--name", "export")
    args = ["cfdi", "draft", "--template", "export", "--total", "50000", "--date", "2026-10-30", "--ref", "tx_1"]
    first = run(capsys, *args)[1]["draft"]
    again = run(capsys, *args)[1]["draft"]
    assert again["id"] == first["id"] and again["unchanged"] is True
    conflict = run(capsys, *args[:5], "51000", *args[6:])[1]
    assert conflict["error"]["code"] == "ref_conflict"
    redo = run(capsys, *args[:5], "51000", *args[6:], "--replace")[1]["draft"]
    assert redo["id"] == first["id"] and redo["total"] == "51000.00"

    draft = Store(tmp / "store").load_draft(redo["id"])
    xml = tmp / "issued.xml"
    xml.write_text(syn.stamped_from_draft(draft, "0F8D2C1A-9999-4A2B-9C3D-000000000009"), encoding="utf-8")
    assert run(capsys, "cfdi", "verify", str(xml), "--draft", redo["id"])[1]["verification"]["matches"] is True
    assert run(capsys, *args)[1]["error"]["code"] == "already_issued"


def test_unknown_folio_asks_for_one(env, capsys):
    tmp, files = env
    raw = cfdi.load(files["export"])
    template, _ = invoices.template_from_cfdi(raw, "export")
    st = Store(tmp / "store")
    st.save_template(template)
    out = run(capsys, "cfdi", "draft", "--template", "export", "--total", "1", "--date", "2026-10-01")[1]
    assert out["error"]["code"] == "unknown_folio"
    out = run(capsys, "cfdi", "draft", "--template", "export", "--total", "1", "--date", "2026-10-01",
              "--folio", "7")[1]
    assert out["draft"]["id"] == "export-A7"


# -- verification ----------------------------------------------------------------------------------------

def _drafted(env, capsys, template_file="rent", name="rent", total="5000"):
    tmp, files = env
    run(capsys, "cfdi", "template", str(files[template_file]), "--name", name)
    d = run(capsys, "cfdi", "draft", "--template", name, "--total", total, "--date", "2026-10-30")[1]["draft"]
    return tmp, Store(tmp / "store").load_draft(d["id"])


def test_verify_accepts_the_matching_invoice_and_records_the_folio(env, capsys):
    tmp, draft = _drafted(env, capsys)
    xml = tmp / "issued.xml"
    xml.write_text(syn.stamped_from_draft(draft, "0F8D2C1A-AAAA-4A2B-9C3D-00000000000A"), encoding="utf-8")
    code, out, text = run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"])
    assert code == 0
    assert_no_personal(text)
    v = out["verification"]
    assert v["matches"] is True and v["failed"] == [] and v["draft"]["status"] == "issued"
    assert v["draft"]["cfdi_id"].startswith("cfdi_")
    assert Store(tmp / "store").state()["last_folio"]["A"] == 152
    again = run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"])[1]["verification"]
    assert again["unchanged"] is True


def test_verify_reports_capture_mistakes_without_showing_personal_values(env, capsys):
    tmp, draft = _drafted(env, capsys)
    xml = tmp / "issued.xml"
    xml.write_text(syn.stamped_from_draft(
        draft, "0F8D2C1A-BBBB-4A2B-9C3D-00000000000B",
        comprobante={"FormaPago": "03"},
        receptor={"Nombre": "ROBERTO SANCHES LUNA"},
        concepto={"Descripcion": "Arrendamiento casa habitación del 1 al 31 de Octubre de 2026"},
    ), encoding="utf-8")
    code, out, text = run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"])
    assert code == 0
    assert_no_personal(text)
    assert "SANCHES" not in text
    v = out["verification"]
    assert v["matches"] is False and v["draft"]["status"] == "pending"
    failed = {f["field"]: f for f in v["failed"]}
    assert failed["FormaPago"]["expected"] == "01" and failed["FormaPago"]["found"] == "03"
    assert "expected" not in failed["Receptor.Nombre"] and "expected" not in failed["Concepto.Descripcion"]
    accepted = run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"], "--accept-differences")[1]
    assert accepted["verification"]["accepted_with_differences"] is True
    assert accepted["verification"]["draft"]["status"] == "issued"


def test_verify_withholdings(env, capsys):
    tmp, draft = _drafted(env, capsys, "company", "acme", "10000.00")
    xml = tmp / "issued.xml"
    xml.write_text(syn.stamped_from_draft(draft, "0F8D2C1A-CCCC-4A2B-9C3D-00000000000C"), encoding="utf-8")
    assert run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"])[1]["verification"]["matches"] is True


def test_an_invoice_links_to_one_draft_only(env, capsys):
    tmp, draft = _drafted(env, capsys)
    xml = tmp / "issued.xml"
    xml.write_text(syn.stamped_from_draft(draft, "0F8D2C1A-DDDD-4A2B-9C3D-00000000000D"), encoding="utf-8")
    run(capsys, "cfdi", "verify", str(xml), "--draft", draft["id"])
    other = run(capsys, "cfdi", "draft", "--template", "rent", "--total", "5000", "--date", "2026-11-30")[1]["draft"]
    out = run(capsys, "cfdi", "verify", str(xml), "--draft", other["id"])[1]
    assert out["error"]["code"] == "uuid_already_linked"


def test_drafts_list_and_discard(env, capsys):
    _, draft = _drafted(env, capsys)
    listed = run(capsys, "cfdi", "drafts", "--status", "pending")[1]["drafts"]
    assert [d["id"] for d in listed] == [draft["id"]]
    assert run(capsys, "cfdi", "discard", draft["id"])[1]["discarded"] == draft["id"]
    assert run(capsys, "cfdi", "drafts")[1]["drafts"] == []


# -- declaration receipts --------------------------------------------------------------------------------

@pytest.mark.parametrize("layout", ["two_columns", "stacked"])
def test_acuse_keeps_amounts_and_dates_and_withholds_identity(tmp_path, capsys, monkeypatch, layout):
    monkeypatch.setenv("MXSAT_KEY", "test-key-not-secret")
    lines = syn.ACUSE_LINES if layout == "two_columns" else syn.ACUSE_LINES_STACKED
    pdf = syn.acuse_pdf(tmp_path / "acuse.pdf", lines)
    code, out, text = run(capsys, "acuse", "read", str(pdf))
    assert code == 0
    assert_no_personal(text)
    a = out["documents"][0]
    assert a["period"] == "septiembre" and a["period_month"] == 9 and a["fiscal_year"] == 2026
    assert a["filed_at"] == "2026-10-07T10:36" and a["due_date"] == "2026-10-23"
    assert a["total_to_pay"] == "1234.00" and a["total_to_pay_cents"] == 123400
    assert a["capture_line"] == "present" and a["capture_line_valid_until"] == "2026-10-26"
    assert a["concepts"][0]["concept"] == "ISR simplificado de confianza. Personas físicas"
    assert a["concepts"][0]["amounts"]["cantidad_a_pagar"] == "1234.00"
    assert a["concepts"][1]["amounts"]["a_cargo"] == "0.00"
    pz_id = run(capsys, "cfdi", "read", str(_write(tmp_path, syn.export_xml())))[1]["documents"][0]["issuer"]["id"]
    assert a["taxpayer_id"] == pz_id


def test_acuse_total_must_match_its_concepts(tmp_path, capsys):
    lines = [ln.replace("$1,234", "$1,235") for ln in syn.ACUSE_LINES]
    out = run(capsys, "acuse", "read", str(syn.acuse_pdf(tmp_path / "acuse.pdf", lines)))[1]
    assert out["error"]["code"] == "acuse_inconsistent"


def test_acuse_rejects_other_pdfs(tmp_path, capsys):
    from reportlab.pdfgen import canvas
    path = tmp_path / "other.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(50, 700, "Estado de cuenta")
    c.save()
    assert run(capsys, "acuse", "read", str(path))[1]["error"]["code"] == "not_an_acuse"


def _write(tmp_path, xml):
    p = tmp_path / "doc.xml"
    p.write_text(xml, encoding="utf-8")
    return p


def test_version(capsys):
    assert run(capsys, "version")[1]["ok"] is True
