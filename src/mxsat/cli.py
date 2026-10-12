"""mxsat command line. Every command prints one JSON document on stdout; errors are JSON too.

Exit codes: 0 ok · 2 invalid input · 3 private store error · 4 output withheld by the privacy check.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, acuse, cfdi, invoices
from .errors import MxsatError
from .privacy import DEFAULT_KEY_ENV, assert_clean, from_env
from .store import Store, store_root


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pseudonym-key-env", default=DEFAULT_KEY_ENV, metavar="NAME",
                        help=f"environment variable holding the pseudonym key (default {DEFAULT_KEY_ENV})")
    store = argparse.ArgumentParser(add_help=False)
    store.add_argument("--store", help="private store folder (default $MXSAT_STORE or ./mxsat-private)")

    p = argparse.ArgumentParser(prog="mxsat", description="Mexican SAT documents for AI agents, personal data kept local.")
    sub = p.add_subparsers(dest="group", required=True)
    sub.add_parser("version", help="print the version")

    c = sub.add_parser("cfdi", help="CFDI invoices (XML)").add_subparsers(dest="cmd", required=True)
    x = c.add_parser("read", parents=[common], help="read stamped invoices; personal data as pseudonyms")
    x.add_argument("files", nargs="+")
    x = c.add_parser("template", parents=[common, store], help="save a private template from a real invoice")
    x.add_argument("file")
    x.add_argument("--name", required=True)
    x.add_argument("--replace", action="store_true")
    c.add_parser("templates", parents=[common, store], help="list templates")
    x = c.add_parser("draft", parents=[common, store], help="exact amounts and a capture sheet from a template")
    x.add_argument("--template", required=True)
    amount = x.add_mutually_exclusive_group(required=True)
    amount.add_argument("--total", help="the amount that reached the bank")
    amount.add_argument("--subtotal")
    x.add_argument("--date", help="invoice date YYYY-MM-DD (default today)")
    x.add_argument("--period", help="YYYY-MM for the month named in the description (default from the template)")
    x.add_argument("--folio", help="folio number (default: next in the series)")
    x.add_argument("--ref", help="what this invoice is for, e.g. the bank deposit id; prevents invoicing it twice")
    x.add_argument("--replace", action="store_true", help="redo the pending draft for this --ref")
    x = c.add_parser("drafts", parents=[common, store], help="list drafts")
    x.add_argument("--status", choices=["pending", "issued"])
    x = c.add_parser("discard", parents=[common, store], help="delete a pending draft")
    x.add_argument("draft")
    x = c.add_parser("verify", parents=[common, store], help="compare the stamped XML with its draft")
    x.add_argument("file")
    x.add_argument("--draft", required=True)
    x.add_argument("--accept-differences", action="store_true",
                   help="record the invoice as issued even if it differs (only with the owner's approval)")

    a = sub.add_parser("acuse", help="declaration receipts (PDF)").add_subparsers(dest="cmd", required=True)
    x = a.add_parser("read", parents=[common], help="read declaration receipts; personal data withheld")
    x.add_argument("files", nargs="+")
    return p


def run(args: argparse.Namespace) -> tuple[dict, list[str]]:
    if args.group == "version":
        return {"ok": True, "version": __version__}, []
    pz = from_env(args.pseudonym_key_env)
    if pz.ephemeral:
        print(f"warning: ${args.pseudonym_key_env} is not set; ids are random and change on every run",
              file=sys.stderr)
    st = Store(store_root(getattr(args, "store", None))) if hasattr(args, "store") else None

    if args.group == "acuse":
        docs, personal = [], []
        for f in args.files:
            view, pv = acuse.read(f, pz)
            docs.append(view)
            personal += pv
        return {"ok": True, "documents": docs}, personal

    if args.cmd == "read":
        docs, personal = [], []
        for f in args.files:
            raw = cfdi.load(f)
            docs.append(cfdi.public_view(raw, pz))
            personal += cfdi.personal_values(raw)
        return {"ok": True, "documents": docs}, personal

    if args.cmd == "template":
        raw = cfdi.load(args.file)
        template, warnings = invoices.template_from_cfdi(raw, args.name)
        if st.template_path(args.name).exists() and not args.replace:
            raise MxsatError("template_exists", f"template {args.name} exists; use --replace")
        st.save_template(template)
        st.record_folio(raw["comprobante"].get("Serie", ""), raw["comprobante"].get("Folio"))
        return ({"ok": True, "template": invoices.template_view(template, pz, warnings)},
                cfdi.personal_values(raw) + invoices.template_personal(template))

    if args.cmd == "templates":
        ts = st.templates()
        return ({"ok": True, "templates": [invoices.template_view(t, pz) for t in ts]},
                [v for t in ts for v in invoices.template_personal(t)])

    if args.cmd == "draft":
        draft, unchanged = invoices.build_draft(
            st, args.template, total=args.total, subtotal=args.subtotal, date=args.date, period=args.period,
            folio=args.folio, ref=args.ref, replace=args.replace)
        sheet = st.draft_path(draft["id"]).with_suffix(".md")
        if not unchanged:
            sheet = st.save_draft(draft, invoices.capture_sheet(draft))
        view = invoices.draft_view(draft, pz, sheet.as_posix())
        view["unchanged"] = unchanged
        return {"ok": True, "draft": view}, invoices.draft_personal(draft)

    if args.cmd == "drafts":
        ds = [d for d in st.drafts() if not args.status or d["status"] == args.status]
        return ({"ok": True, "drafts": [invoices.draft_view(d, pz) for d in ds]},
                [v for d in ds for v in invoices.draft_personal(d)])

    if args.cmd == "discard":
        d = invoices.discard_draft(st, args.draft)
        return {"ok": True, "discarded": d["id"]}, invoices.draft_personal(d)

    if args.cmd == "verify":
        raw = cfdi.load(args.file)
        result = invoices.verify(st, raw, args.draft, args.accept_differences)
        d = result["draft"]
        return ({"ok": True, "verification": {
            "draft": invoices.draft_view(d, pz),
            "matches": result["matches"],
            "accepted_with_differences": bool(d["verification"] and d["verification"]["accepted_with_differences"]),
            "checks_passed": result["passed"],
            "failed": result["failed"],
            "warnings": result["warnings"],
            "unchanged": result["unchanged"],
        }}, invoices.draft_personal(d) + cfdi.personal_values(raw))

    raise MxsatError("bad_command", "unknown command")  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        payload, personal = run(args)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        assert_clean(text, personal)
    except MxsatError as e:
        print(json.dumps({"ok": False, "error": {"code": e.code, "message": e.message}}, ensure_ascii=False))
        return e.exit_code
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
