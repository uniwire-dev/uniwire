"""Links that open a document in the uniwire web editor.

The document travels in the fragment of the link (``#doc=``, base64url of the raw-deflated JSON text): the
browser never sends it to the server. The editor draws it with the reference library (single-line and
multi-line), shows the rule findings and offers PDF / SVG downloads.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

#: The hosted web editor.
VIEWER_URL = "https://uniwire.sh/viewer/"

#: Above this length a link is not returned by the MCP tools (assistants copy links into chat replies).
MAX_LINK_CHARS = 60_000


def viewer_link(document: dict[str, Any] | str, base: str = VIEWER_URL, pdf: bool = False) -> str:
    """Link opening ``document`` (a JSON object, or its JSON text kept as is) in the web editor at ``base``.
    ``pdf``: the editor also downloads the PDF of the drawing once it is rendered."""
    text = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    c = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate, as CompressionStream("deflate-raw")
    data = c.compress(text.encode("utf-8", "replace")) + c.flush()  # lone surrogates become "?"
    link = base + "#doc=" + base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return link + "&download=pdf" if pdf else link


def document_from_link(link: str) -> str:
    """JSON text carried by a ``#doc=`` link (inverse of :func:`viewer_link`)."""
    _, sep, payload = link.partition("#doc=")
    payload = payload.partition("&")[0]
    if not sep:
        raise ValueError("not a uniwire editor link (no '#doc=')")
    data = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    d = zlib.decompressobj(-15)
    text = d.decompress(data, 5_000_000)  # the editor's own inflate cap
    if d.unconsumed_tail:
        raise ValueError("document too large")
    return text.decode("utf-8")
