"""The private store: templates, drafts and folio state, as plain JSON files on the owner's computer.

The store holds personal data (RFCs, names, addresses). Keep it out of version control and out of the AI
agent's reach (e.g. a deny rule for the folder in the agent's settings). It is not encrypted.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .errors import STORE_ERROR, MxsatError

DEFAULT_STORE = "mxsat-private"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

README = """mxsat private store

These files contain personal data: RFCs, names, postal codes and invoice details.
- Do not commit this folder (it has its own .gitignore).
- Do not let an AI agent read it; the mxsat commands show the agent only pseudonyms.
- It is not encrypted. Back it up like any personal document.

Capture sheets for the SAT invoicing portal are in drafts/*.md.
"""


def store_root(arg: str | None) -> Path:
    return Path(arg or os.environ.get("MXSAT_STORE") or DEFAULT_STORE)


class Store:
    def __init__(self, root: Path):
        self.root = root

    # -- files ---------------------------------------------------------------------------------------
    def ensure(self) -> None:
        try:
            (self.root / "templates").mkdir(parents=True, exist_ok=True)
            (self.root / "drafts").mkdir(parents=True, exist_ok=True)
            ignore = self.root / ".gitignore"
            if not ignore.exists():
                ignore.write_text("*\n", encoding="utf-8")
            readme = self.root / "README.txt"
            if not readme.exists():
                readme.write_text(README, encoding="utf-8")
        except OSError:
            raise MxsatError("store_not_writable", "cannot create the private store folder", STORE_ERROR) from None

    def _read(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, ValueError):
            raise MxsatError("store_corrupt", f"cannot read {path.relative_to(self.root).as_posix()}", STORE_ERROR) from None

    def _write(self, path: Path, data: dict | str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            raise MxsatError("store_not_writable", "cannot write to the private store", STORE_ERROR) from None

    # -- templates -----------------------------------------------------------------------------------
    @staticmethod
    def check_name(name: str, what: str = "template name") -> str:
        if not NAME_RE.match(name or ""):
            raise MxsatError("bad_name", f"{what} must be 1-40 lowercase letters, digits or hyphens")
        return name

    def template_path(self, name: str) -> Path:
        return self.root / "templates" / f"{self.check_name(name)}.json"

    def load_template(self, name: str) -> dict:
        try:
            return self._read(self.template_path(name))
        except FileNotFoundError:
            raise MxsatError("template_not_found", f"no template named {name}") from None

    def save_template(self, template: dict) -> None:
        self.ensure()
        self._write(self.template_path(template["name"]), template)

    def templates(self) -> list[dict]:
        folder = self.root / "templates"
        return [self._read(p) for p in sorted(folder.glob("*.json"))] if folder.exists() else []

    # -- drafts --------------------------------------------------------------------------------------
    def draft_path(self, draft_id: str) -> Path:
        if not re.match(r"^[a-z0-9-]+-[A-Za-z0-9]*\d+$", draft_id or ""):
            raise MxsatError("bad_draft_id", "not a draft id")
        return self.root / "drafts" / f"{draft_id}.json"

    def load_draft(self, draft_id: str) -> dict:
        try:
            return self._read(self.draft_path(draft_id))
        except FileNotFoundError:
            raise MxsatError("draft_not_found", f"no draft {draft_id}") from None

    def save_draft(self, draft: dict, sheet: str) -> Path:
        self.ensure()
        path = self.draft_path(draft["id"])
        self._write(path, draft)
        sheet_path = path.with_suffix(".md")
        self._write(sheet_path, sheet)
        return sheet_path

    def delete_draft(self, draft_id: str) -> None:
        path = self.draft_path(draft_id)
        for p in (path, path.with_suffix(".md")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                raise MxsatError("store_not_writable", "cannot delete the draft", STORE_ERROR) from None

    def drafts(self) -> list[dict]:
        folder = self.root / "drafts"
        return [self._read(p) for p in sorted(folder.glob("*.json"))] if folder.exists() else []

    # -- folios --------------------------------------------------------------------------------------
    def state(self) -> dict:
        try:
            return self._read(self.root / "state.json")
        except FileNotFoundError:
            return {"last_folio": {}}

    def record_folio(self, series: str | None, folio: str | None) -> None:
        if not folio or not folio.isdigit():
            return
        self.ensure()
        state = self.state()
        key = series or ""
        state["last_folio"][key] = max(int(folio), state["last_folio"].get(key, 0))
        self._write(self.root / "state.json", state)
