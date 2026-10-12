# Changelog

## 0.1.0 — first version

- `cfdi read`: CFDI 3.3/4.0 to JSON with parties, places, descriptions and UUIDs as HMAC pseudonyms.
- `cfdi template`: private templates from real invoices; learns month placeholders in the description and the
  offset between issue date and period.
- `cfdi draft`: exact amounts from the deposit (subtotal search that lands on the total after rounding),
  period with the month's last day, next folio, a subset of CFDI 4.0 rules, a capture sheet in the SAT
  portal's order; `--ref` makes it idempotent and refuses to invoice the same deposit twice.
- `cfdi verify`: stamped XML against its draft, field by field; personal differences are reported without
  values; `--accept-differences` records it anyway.
- `cfdi templates`, `drafts`, `discard`.
- `acuse read`: declaration receipts (PDF), with the capture line, operation number, RFC and name withheld;
  the total is checked against the concepts.
- Fail-closed privacy check on every output (exit code 4). Private-data guard for commits and CI.
- Verified with the owner's real September 2026 invoices: both rebuilt from their templates with 42 of 42
  checks matching.
