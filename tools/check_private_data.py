"""Private-data guard: blocks commits with SAT documents or personal data.

Fails if a file is an invoice or receipt (``.xml``, ``.pdf``), lives in a private store, or contains an RFC,
CURP or e-mail address that is not declared as fictitious in ``.pii-allowlist``. It prints the file, line
and kind, never the value.

    python tools/check_private_data.py            # staged files
    python tools/check_private_data.py FILE...    # these files (CI passes every versioned file)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RFC_RE = re.compile(r"\b([A-ZÑ&]{3,4})(\d{2})(\d{2})(\d{2})([A-Z0-9]{3})\b")
CURP_RE = re.compile(r"\b[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})\b")
EMAIL_OK = {"example.com", "example.org", "users.noreply.github.com"}


def problems_in(text: str, allow: set[str]) -> list[tuple[int, str]]:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in RFC_RE.finditer(line):
            if 1 <= int(m.group(3)) <= 12 and 1 <= int(m.group(4)) <= 31 and m.group(0) not in allow:
                found.append((n, "RFC"))
        for m in CURP_RE.finditer(line):
            if m.group(0) not in allow:
                found.append((n, "CURP"))
        for m in EMAIL_RE.finditer(line):
            if m.group(1).lower() not in EMAIL_OK and m.group(0) not in allow:
                found.append((n, "e-mail"))
    return found


def _staged() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                         cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def _read(path: str, staged: bool) -> bytes:
    if staged:
        return subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, check=True).stdout
    return (ROOT / path).read_bytes()


def main(argv: list[str]) -> int:
    staged = not argv
    allow_file = ROOT / ".pii-allowlist"
    allow = {ln.strip() for ln in allow_file.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")} if allow_file.exists() else set()
    problems = []
    for path in (_staged() if staged else argv):
        norm = path.replace("\\", "/")
        if norm == ".pii-allowlist":
            continue
        if "mxsat-private/" in norm or norm.lower().endswith((".xml", ".pdf")):
            problems.append(f"{norm}: SAT documents and private stores are never versioned")
            continue
        data = _read(norm, staged)
        if b"\0" in data[:8192]:
            continue
        for n, kind in problems_in(data.decode("utf-8", errors="replace"), allow):
            problems.append(f"{norm}:{n}: possible {kind}")
    if problems:
        print("check_private_data: blocked, possible personal data:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("If it is a fictitious test value, build it in code or add it to .pii-allowlist.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1:]))
