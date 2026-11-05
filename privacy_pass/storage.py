"""Session registry persistence.

Alias mappings are sensitive (they restore private values), so the store:

- writes JSON with owner-only permissions (0600 file, 0700 directory),
- keys files by a SHA-256 of the session id (no traversal, no raw ids),
- supports delete and purge so retention is explicit and testable.

Default location follows the Hermes plugin-data convention
(``~/.hermes/plugins_data/privacy-pass/sessions``); override with
``PRIVACY_PASS_STORE_DIR``. Plain JSON is not encryption; it is minimal,
permission-restricted storage, per README hard requirement 3.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def default_store_dir() -> Path:
    override = os.environ.get("PRIVACY_PASS_STORE_DIR")
    if override:
        return Path(override).expanduser()
    # Follow HERMES_HOME so sandboxed/data-root installs keep state in their
    # own data area; fall back to the standard per-user location.
    hermes_home = os.environ.get("HERMES_HOME")
    base = Path(hermes_home) if hermes_home else Path.home() / ".hermes"
    return base / "plugins_data" / "privacy-pass" / "sessions"


class SessionStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_store_dir()

    def _ensure_dir(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        return self.root

    def path_for(self, session_id: str) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return self._ensure_dir() / f"{digest}.json"

    def save(self, session_id: str, snapshot: dict) -> None:
        path = self.path_for(session_id)
        payload = json.dumps(snapshot, ensure_ascii=False)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def load(self, session_id: str) -> dict | None:
        path = self.path_for(session_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def delete(self, session_id: str) -> bool:
        path = self.path_for(session_id)
        if path.exists():
            path.unlink(missing_ok=True)
            return True
        return False

    def purge(self, max_age_days: int | None = None) -> int:
        """Delete session files; with max_age_days, only older ones. Returns
        the number of files removed."""
        if not self.root.is_dir():
            return 0
        removed = 0
        cutoff = time.time() - max_age_days * 86400 if max_age_days else None
        for path in self.root.glob("*.json"):
            try:
                if cutoff is not None and path.stat().st_mtime >= cutoff:
                    continue
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed
