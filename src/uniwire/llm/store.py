"""Short links for the hosted MCP server: documents kept on disk for a limited time.

Assistants copy links into their replies token by token, and a long ``#doc=`` payload does not survive that copy.
With ``uniwire-mcp --store DIR``, the links returned by the tools are short instead
(``https://uniwire.sh/viewer/#d=<id>``): the server keeps the document text in ``DIR`` and serves it at
``GET /doc/<id>``. The id is derived from the content (the same document gives the same link) and cannot be
guessed without it. Documents expire ``ttl_days`` after their last use; the store also bounds the total size by
removing the oldest documents first. Anyone holding a link may delete its document before then: an empty marker
``<id>.deleted`` remains for ``ttl_days`` so that the link can say so, and storing the same text again (a new
request from an assistant) removes it.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ID_LENGTH = 12  # 62**12 ~ 3e21
ID_RE = re.compile(rf"^[0-9A-Za-z]{{{ID_LENGTH}}}$")


def doc_id(text: str) -> str:
    """Content-derived id of a document text (base62 of its SHA-256, truncated)."""
    n = int.from_bytes(hashlib.sha256(text.encode("utf-8", "replace")).digest(), "big")
    out = []
    for _ in range(ID_LENGTH):
        n, r = divmod(n, 62)
        out.append(_ALPHABET[r])
    return "".join(out)


class DocStore:
    """Document texts in ``root`` (one file per id), expired after ``ttl_days`` without use."""

    def __init__(self, root: str | Path, ttl_days: float = 30, max_total_bytes: int = 500_000_000,
                 max_doc_bytes: int = 2_000_000) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_s = ttl_days * 86400
        self.max_total_bytes = max_total_bytes
        self.max_doc_bytes = max_doc_bytes
        self._last_prune = 0.0

    def _path(self, id_: str) -> Path:
        return self.root / f"{id_}.json"

    def put(self, text: str) -> Optional[str]:
        """Store ``text`` and return its id (None when it is larger than ``max_doc_bytes``)."""
        data = text.encode("utf-8", "replace")
        if len(data) > self.max_doc_bytes:
            return None
        id_ = doc_id(text)
        path = self._path(id_)
        self._marker(id_).unlink(missing_ok=True)  # stored again after a deletion: a new request
        if path.exists():
            os.utime(path)  # used again: the expiry restarts
        else:
            fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        if time.time() - self._last_prune > 3600:
            self.prune()
        return id_

    def get(self, id_: str) -> Optional[str]:
        """The stored text, or None (unknown, malformed or expired id)."""
        if not ID_RE.match(id_ or ""):
            return None
        path = self._path(id_)
        try:
            if time.time() - path.stat().st_mtime > self.ttl_s:
                path.unlink(missing_ok=True)
                return None
            return path.read_text("utf-8")
        except FileNotFoundError:
            return None

    def _marker(self, id_: str) -> Path:
        return self.root / f"{id_}.deleted"

    def delete(self, id_: str) -> bool:
        """Remove a stored document at the request of a link holder; False when there is nothing to remove
        (unknown, malformed or expired id)."""
        if not ID_RE.match(id_ or ""):
            return False
        path = self._path(id_)
        if not path.exists():
            return False
        self._marker(id_).touch()
        path.unlink(missing_ok=True)
        return True

    def deleted(self, id_: str) -> bool:
        """Whether the document of ``id_`` was deleted at the request of a link holder (within ``ttl_days``)."""
        if not ID_RE.match(id_ or ""):
            return False
        try:
            return time.time() - self._marker(id_).stat().st_mtime <= self.ttl_s
        except FileNotFoundError:
            return False

    def prune(self) -> None:
        """Remove expired documents, then the oldest ones while the store is over ``max_total_bytes``."""
        self._last_prune = now = time.time()
        files = []
        for p in self.root.iterdir():
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            if p.suffix == ".tmp" and now - st.st_mtime > 3600 or p.suffix in (".json", ".deleted") and now - st.st_mtime > self.ttl_s:
                p.unlink(missing_ok=True)
            elif p.suffix == ".json":
                files.append((st.st_mtime, st.st_size, p))
        total = sum(size for _, size, _ in files)
        for _, size, p in sorted(files):
            if total <= self.max_total_bytes:
                break
            p.unlink(missing_ok=True)
            total -= size
