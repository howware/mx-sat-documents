# Using mxsat from an AI agent

For agents (Claude Code, Codex…) that use `mxsat` on behalf of its owner. A howware's protocol
(for example an invoicing howware) decides *when* to call each command; this page says *how*.

## Rules

1. **Never open SAT documents yourself.** Don't read the `.xml` or `.pdf` files with your own tools or scripts:
   their content would reach your context with every personal value in it. Use `mxsat`, which returns only what
   is safe to see.
2. **Never read the private store** (`mxsat-private/` or `$MXSAT_STORE`). It holds templates and capture sheets
   with real RFCs, names and addresses. Tell the owner the sheet's path; **they** open it.
3. **Never ask for, print or write the pseudonym key.** `MXSAT_KEY` lives in the owner's environment.
4. **Amounts come from data, never retyped.** Pass the deposit amount exactly as the bank statement adapter gave
   it, and pass the deposit's id as `--ref`.
5. **Approval before records.** Creating a template, a draft, or accepting a verification with differences
   (`--accept-differences`) changes the owner's records: show what will happen and wait for a yes.
6. **Tax decisions are not yours.** If a new client or concept needs a template, the owner (with their
   accountant) decides the taxes; take the template from an invoice they already issued.

## Owner setup (once)

Deny the agent direct access to SAT documents and to the store. In Claude Code, in the project's
`.claude/settings.json`:

```json
{
  "permissions": {
    "deny": ["Read(**/*.pdf)", "Read(**/*.xml)", "Read(**/mxsat-private/**)"]
  }
}
```

## Commands

| Command | When | Output to use |
|---|---|---|
| `mxsat cfdi read F.xml…` | To know what an invoice says | `documents[]`: `id` (from the UUID), `series`, `folio`, `total_cents`, `payment_form`, `receiver.id`, `concepts[].transfers` |
| `mxsat cfdi template F.xml --name N` | First month with a client or concept, from the last real invoice | `template.receiver_id` (link it to the bank counterparty), `period.offset_months`, `warnings` |
| `mxsat cfdi templates` | To pick a template | `templates[]` |
| `mxsat cfdi draft --template N --total X --ref R [--date D] [--period YYYY-MM]` | A deposit needs an invoice | `draft.id`, `subtotal`, `transfers`, `withholdings`, `total`, `period`, `capture_sheet` (a path for the owner) |
| `mxsat cfdi verify F.xml --draft ID` | The owner has the stamped XML | `verification.matches`, `failed[]` (`expected`/`found` only for non-personal fields), `warnings[]` |
| `mxsat cfdi drafts [--status pending\|issued]` | Month-end: what's still pending | `drafts[]` |
| `mxsat cfdi discard ID` | A pending draft is no longer wanted | `discarded` |
| `mxsat acuse read F.pdf` | The accountant sent the declaration receipt | `due_date`, `total_to_pay_cents`, `concepts[]`, `capture_line_valid_until` |

## Errors worth handling

| `error.code` | Meaning | What to do |
|---|---|---|
| `already_issued` | This `--ref` was already invoiced | Tell the owner; never create a second invoice for it |
| `ref_conflict` | This `--ref` has a pending draft with other values | Ask; `--replace` only with approval |
| `no_exact_subtotal` | No subtotal gives exactly that total after rounding | Show the nearest totals; ask the owner |
| `unknown_folio` | No previous folio for the series | Ask the owner for the last folio used; pass `--folio` |
| `template_breaks_rules` | The draft would break a CFDI 4.0 rule | Show the message; the template needs the owner's review |
| `uuid_already_linked` | That stamped XML belongs to another draft | Ask which deposit it is for |
| `privacy_check_failed` (exit 4) | Output withheld: it would contain personal data | Stop; don't work around it; it's a bug to report |

A warning on stderr about `MXSAT_KEY` means ids are random for this run: don't store them.
