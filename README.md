<h1 align="center">mxsat · Mexican SAT documents for AI agents, personal data kept local</h1>

<p align="center">
  <b>Reads CFDI invoices and declaration receipts, prepares the next invoice exactly, and checks what was stamped,
  while your RFC, names and addresses stay on your computer.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/mx-sat-documents/actions/workflows/ci.yml"><img src="https://github.com/howware/mx-sat-documents/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version 0.1.0">
  <a href="https://howware.org"><img src="https://img.shields.io/badge/howware-adapter-5a45d6" alt="howware adapter"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.es.md">Español</a> · <a href="docs/agent.md">Guide for AI agents</a></p>

> **A [howware](https://howware.org) adapter.** A howware is your know-how put to work by AI. Its core (the
> protocol and your rules) knows nothing about files, portals or databases; **adapters** connect it to that
> environment, like ports and adapters in clean architecture. `mxsat` is the adapter for SAT documents. It holds
> no tax rules: whether an income is taxed at 0 %, exempt or withheld comes from invoices you already issued.

```text
mxsat cfdi read factura.xml          # an invoice, as JSON: amounts, codes, taxes; people as pseudonyms
mxsat cfdi template factura.xml --name renta     # a private template from a real invoice
mxsat cfdi draft --template renta --total 5000 --ref <deposit id>   # exact amounts + a capture sheet
mxsat cfdi verify nueva.xml --draft renta-A152   # did the portal get exactly what was approved?
mxsat acuse read acuse.pdf           # declaration receipt: period, amounts, due date
```

## Why

Invoicing every month is copying: a deposit reaches the bank, and its amount, the client's data, the concept and
the period go into the SAT portal by hand. A wrong digit, the wrong payment form or last month's period are
silent mistakes, found later by your accountant, or by the SAT.

`mxsat` does the exact part. An AI agent does the judgment part (which deposit is which client, what to invoice),
following your rules.

## What it does

| Command | Does |
|---|---|
| `cfdi read` | Reads stamped CFDI 3.3/4.0 XML: type, series and folio, dates, payment form and method, totals in cents, concepts with product and unit codes, transferred and withheld taxes, related invoices. Parties, places and descriptions come out as pseudonyms |
| `cfdi template` | Saves a **private template** from a real invoice: receiver, concept, taxes, payment form, property tax account. If the description names a month (*del 1 al 31 de octubre de 2026*), it learns the placeholders and the offset from the issue date |
| `cfdi draft` | Applies a template to an amount: **from the deposit** (`--total`) it finds the subtotal whose taxes, rounded to cents like the portal does, give exactly that total. Fills the period (last day of the month included), takes the next folio, checks a set of CFDI 4.0 rules, and writes a **capture sheet** in the portal's order. With `--ref`, the same deposit can't be invoiced twice |
| `cfdi verify` | Compares the stamped XML with the approved draft, **field by field** (42 checks for a one-concept invoice). Shows the codes and amounts that differ; personal fields only say *differs* |
| `cfdi templates` · `drafts` · `discard` | List templates and drafts; discard a pending draft |
| `acuse read` | Reads the PDF of a declaration receipt (*acuse de recibo*): declaration type, period, filing date, due date, each tax concept with its amounts, total to pay and capture-line validity. Checks the total against the concepts |

Every command prints JSON on stdout; errors are JSON too. Exit codes: `0` ok, `2` invalid input, `3` private
store error, `4` output withheld by the privacy check.

## Privacy

| Stays on your computer | What the agent sees |
|---|---|
| The XML and PDF files; the private store (templates, drafts, capture sheets) | Amounts, dates, SAT codes, tax rates, payment form, series and folio |
| RFCs, names, postal codes, foreign tax ids, descriptions, property tax accounts, UUIDs, capture lines, operation numbers | Pseudonyms: `party_…`, `cfdi_…`, `place_…`; "present" for a capture line or a foreign tax id |

How it works, and its limits:
- **Pseudonyms are HMACs** of the real values with a key you keep in an environment variable (`MXSAT_KEY`).
  With the key they are stable across runs; without it, they change every time and a warning says so.
- **Fail-closed.** Before printing, the output is checked against every personal value of the documents
  involved and for RFC, CURP and e-mail shapes. A hit withholds the output (exit code 4).
- **The private store is plain JSON, not encrypted.** It has its own `.gitignore`. Keep it out of your agent's
  reach with a deny rule (see the [agent guide](docs/agent.md)); `mxsat` cannot enforce that on its own.
- **What the agent sees leaves your computer** for your AI provider, under its terms: amounts, dates and the
  kind of income can't be hidden, because without them nothing can be reconciled.
- Data the portal and the SAT receive when you invoice is outside this tool.

All the code is open, so all of this can be checked. Please report privacy problems privately
([SECURITY.md](SECURITY.md)).

## Install

```bash
uv tool install git+https://github.com/howware/mx-sat-documents
```

Set a pseudonym key once (any long random text; keep a copy, as with a password):

```powershell
[Environment]::SetEnvironmentVariable("MXSAT_KEY", "<long random text>", "User")   # Windows
```

```bash
export MXSAT_KEY="<long random text>"   # macOS / Linux, in your shell profile
```

The store defaults to `./mxsat-private`; set `MXSAT_STORE` or pass `--store` to change it.

## Limits

- **It does not stamp or cancel invoices.** You capture the sheet in the SAT portal (or with your provider) and
  give the stamped XML back for verification. Stamping through an authorized provider (PAC) is planned.
- Templates: income invoices, CFDI 4.0, MXN, one concept with quantity 1, no global invoices or third-party
  concepts. `read` accepts any CFDI 3.3/4.0.
- The rules it checks are a subset of the CFDI 4.0 rules, not a full validator; the SAT has the last word.
- `acuse read` is tested with the 2026 layout of the monthly provisional declaration receipt.
- **It is not tax advice** and is not affiliated with the SAT. Your accountant decides how each income is taxed.

## Development

```bash
uv sync
uv run pytest -q                                    # synthetic documents only
uvx ruff check src tests tools
git config core.hooksPath tools/git-hooks           # blocks commits with SAT documents or personal data
```

Rules for people and agents working on this repository: [AGENTS.md](AGENTS.md).

## License

[Apache 2.0](LICENSE).
