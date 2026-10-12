import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_private_data", Path(__file__).resolve().parents[1] / "tools" / "check_private_data.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_guard_flags_rfc_curp_and_email_but_not_allowed_values():
    rfc = "GOD" + "E561231" + "GR8"
    curp = "GODE" + "561231" + "HDFRRN09"
    text = f"a {rfc}\nb {curp}\nc someone@" + "mail.com\nd XAXX010101000\ne 81111504\n"
    kinds = guard.problems_in(text, {"XAXX010101000"})
    assert kinds == [(1, "RFC"), (2, "CURP"), (3, "e-mail")]


def test_guard_blocks_sat_documents():
    assert guard.main(["factura.xml"]) == 1
    assert guard.main(["mxsat-private/templates/x.json"]) == 1
