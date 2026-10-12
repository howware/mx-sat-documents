# AGENTS.md

Instructions for AI agents (and people) **developing** this repository. To **use** `mxsat` from an agent,
see [docs/agent.md](docs/agent.md).

## Golden rule: real SAT documents are never read directly or versioned

Real invoices and receipts contain the owner's RFC, name and address, and those of their clients and tenants.

- **Do not open or extract text from a real XML or PDF** with your own tools or scripts. Use `mxsat`, whose
  output is pseudonymized and checked.
- To debug a parser against a real document, print only booleans, counts and **masked shapes** (`9` for each
  digit, `X` for each letter inside tokens that contain digits), never values. Write such scripts outside the
  repository and delete them afterwards.
- A store created while testing with real documents goes in a temporary folder and is deleted when done.
- Tests use synthetic documents built in `tests/synthetic.py`. Every person, RFC, address and number there is
  invented; RFC-shaped values are assembled in code so the guard doesn't flag them.

## Private-data guard

```bash
git config core.hooksPath tools/git-hooks
```

[tools/check_private_data.py](tools/check_private_data.py) blocks `.xml`/`.pdf` files, private stores and any RFC,
CURP or e-mail not in `.pii-allowlist`. CI runs it on every versioned file. Never add a real value to the
allowlist.

## Commands

```bash
uv sync
uv run pytest -q
uvx ruff@0.6.9 check src tests tools
uv run mxsat --help
```

## Architecture

`cfdi.load` (XML → raw dict with the SAT's attribute names, **with personal data**) → `cfdi.public_view` or
`invoices` (templates, drafts, verification against the private `store`) → `cli` serializes →
`privacy.assert_clean` (fail-closed against every personal value of the documents involved; exit 4).
`acuse` does the same for declaration receipts. The raw structures are never printed.

## Conventions

- This is an **adapter**: no tax rules in code. Rates, exemptions and payment forms come from templates taken
  from real invoices; the code only computes, checks CFDI rules and compares.
- Amounts are `Decimal`, rounded half-up to cents; never `float`.
- Code, comments, docs and messages in English; SAT terms (`FormaPago`, `UsoCFDI`…) and capture-sheet labels
  in Spanish, as the SAT writes them. READMEs in English and Spanish.
- A new output field needs: its place in the privacy check (is it personal?), a test that it doesn't leak, and
  the README tables.
- Error messages never include values from a document.
- Commits without AI-tool attribution lines.
