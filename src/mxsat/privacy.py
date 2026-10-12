"""Pseudonyms and the fail-closed leak check.

Personal values (RFCs, names, postal codes, foreign tax ids, descriptions, property tax accounts, UUIDs,
capture lines) never reach stdout. Parties and documents are named by an HMAC of their real values with a
key the owner keeps in an environment variable, so ids are stable across runs and across tools that share
the key. Before anything is printed, the output is scanned for every personal value of the documents
involved and for RFC, CURP and e-mail shapes; a hit aborts with exit code 4.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import unicodedata

from .errors import PRIVACY_ERROR, MxsatError

DEFAULT_KEY_ENV = "MXSAT_KEY"

GENERIC_RFCS = {
    "XAXX010101000": "generic_public",
    "XEXX010101000": "generic_foreign",
}

RFC_RE = re.compile(r"\b([A-ZÑ&]{3,4})(\d{2})(\d{2})(\d{2})([A-Z0-9]{3})\b")
CURP_RE = re.compile(r"\b[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})\b")


def norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).upper().split())


class Pseudonymizer:
    def __init__(self, key: bytes | None):
        self.ephemeral = key is None
        self._key = key if key is not None else secrets.token_bytes(32)

    def id(self, kind: str, *parts: str | None) -> str:
        msg = "\x1f".join([kind, *(norm(p or "") for p in parts)]).encode("utf-8")
        return f"{kind}_{hmac.new(self._key, msg, hashlib.sha256).hexdigest()[:12]}"

    def party(self, rfc: str | None, name: str | None = None, foreign_id: str | None = None) -> str:
        """A generic RFC is shared by many people, so its id also uses the name and foreign tax id."""
        rfc = norm(rfc or "")
        if rfc in GENERIC_RFCS:
            return self.id("party", rfc, name, foreign_id)
        return self.id("party", rfc)


def from_env(env_name: str) -> Pseudonymizer:
    value = os.environ.get(env_name)
    return Pseudonymizer(value.encode("utf-8") if value else None)


def rfc_kind(rfc: str | None) -> str | None:
    if not rfc:
        return None
    rfc = norm(rfc)
    if rfc in GENERIC_RFCS:
        return GENERIC_RFCS[rfc]
    return {13: "person", 12: "company"}.get(len(rfc), "unknown")


def find_leaks(text: str, personal: list[str]) -> list[str]:
    """Kinds of personal data found in ``text`` (never the values)."""
    kinds: list[str] = []
    upper = norm(text)
    for value in personal:
        v = norm(value or "")
        if not v or v in GENERIC_RFCS:
            continue
        if v.isdigit():
            if len(v) >= 5 and re.search(rf"(?<![\w.]){re.escape(v)}(?![\w.])", upper):
                kinds.append("document_value")
        elif len(v) >= 6 and v in upper:
            kinds.append("document_value")
    for m in RFC_RE.finditer(text):
        if m.group(0) not in GENERIC_RFCS and 1 <= int(m.group(3)) <= 12 and 1 <= int(m.group(4)) <= 31:
            kinds.append("rfc")
    if CURP_RE.search(text):
        kinds.append("curp")
    for m in EMAIL_RE.finditer(text):
        if m.group(1).lower() not in {"example.com", "example.org"}:
            kinds.append("email")
    return sorted(set(kinds))


def assert_clean(text: str, personal: list[str]) -> None:
    kinds = find_leaks(text, personal)
    if kinds:
        raise MxsatError(
            "privacy_check_failed",
            "output withheld: it would contain personal data (" + ", ".join(kinds) + "). Please report this as a bug.",
            PRIVACY_ERROR,
        )
