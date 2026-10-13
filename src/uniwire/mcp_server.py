"""MCP server exposing uniwire to LLM assistants (``uniwire-mcp``, stdio transport).

Install with the ``mcp`` extra (``pip install "uniwire[mcp]"``), then register the command in any
MCP client, e.g. ``claude mcp add uniwire -- uniwire-mcp`` or, in a client configuration file::

    {"mcpServers": {"uniwire": {"command": "uniwire-mcp"}}}

Tools take documents as JSON objects, JSON strings or file paths; the tool logic lives in
:mod:`uniwire.llm.tools` (importable without the MCP SDK).
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import sys
import time
from typing import Any, Optional, Union

from . import __version__
from .llm import tools as T

Document = Union[dict[str, Any], str]

log = logging.getLogger("uniwire.mcp")

INSTRUCTIONS = (
    "uniwire draws and checks electrical diagrams: single-line diagrams (schéma unifilaire) and multi-line "
    "diagrams of electrical panels and installations (tableau électrique, distribution board, switchboard), with "
    "rule checks (NF C 15-100, IEC 60364), bills of materials and wire lists. Use it whenever the user asks for an "
    "electrical diagram, a panel layout or a check of protections, cables and RCDs. A document is JSON: a power "
    "tree (sources -> devices -> loads, each node in its parent's 'children') plus 'links' for anything outside the "
    "tree. Read the reference card (get_reference_card or resource uniwire://card) before writing a document. "
    "Workflow: write the document, call check (it validates too), fix the findings (apply_patch edits nodes by "
    "id), then give the user the links. describe gives a compact outline with the stable ids to use in patches. "
    "validate, check, apply_patch and render return 'viewer_url' and 'pdf_url': always give them to the user as "
    "clickable links. viewer_url opens the document in the uniwire web editor (drawing, findings, PDF and SVG "
    "downloads); pdf_url gives the PDF drawn by uniwire. They are two different links: when the user asks for a "
    "PDF, give pdf_url exactly as returned, as its own link, "
    "and never draw a PDF yourself. When you report check results, say once, in one sentence, that they "
    "are automatic checks and not a conformity certificate, and that a qualified electrician must verify the "
    "installation (the result's 'scope'); do not repeat it."
)

DESIGN_PROMPT = """You are designing an electrical installation in the uniwire format (it renders as single-line and multi-line diagrams).

Project brief: {brief}

1. Read the uniwire reference card (tool get_reference_card, or resource uniwire://card).
2. If the brief does not say, ask the user for: country / standard (rule profile, e.g. nfc15100, iec60364),
   earthing system (TT, TN-S, TN-C-S, IT), supply (single-phase 1P+N 230 V or three-phase 3P+N 400 V,
   subscribed power or main protection rating), and the list of loads / rooms / circuits.
   If the user prefers, make reasonable, standard-compliant assumptions and state them in meta.notes.
3. Write the complete document: installation, profiles, a tree from the source through the main device
   and the board(s) down to every load, explicit ids on every node you reference, cables on final circuits,
   links for second sources, control and interlocks. Use templates for repeated devices.
4. Call validate and fix every issue.
5. Call check and fix every error (and warnings where sensible); use apply_patch for targeted edits.
6. Call describe to review the result, then give the user the document, the viewer_url and pdf_url returned
   by check (clickable links: drawing and findings, PDF), a summary of the assumptions and the remaining
   findings, and one sentence saying that these are automatic checks, not a conformity certificate, and that a
   qualified electrician must verify the installation.
"""


def _sdk():
    """(server class, ToolError class) of the installed MCP SDK."""
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        return MCPServer, ToolError
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError
        return FastMCP, ToolError


#: Tools that process a document: in public mode they run in the worker pool (:mod:`uniwire.llm.sandbox`).
#: Each server tool calls the function of the same name and arguments in :mod:`uniwire.llm.tools`.
POOLED = {"validate", "check", "describe", "apply_patch", "render", "wiring", "bom", "normalize", "viewer_link"}

#: Website and icon announced to clients (app directories and chat interfaces show them).
WEBSITE_URL = "https://uniwire.sh"
ICON_URL = "https://uniwire.sh/assets/brand/icon-512.png"

#: Tools whose results carry viewer_url / pdf_url (with a store, they keep the document for the links).
LINKED = {"validate", "check", "apply_patch", "render", "viewer_link"}

#: Request body limit of the public HTTP server (checked before the JSON is parsed).
MAX_REQUEST_BODY_BYTES = 3 * 1024 * 1024


def _shorten(result: Any, store, base: str, pdf_base: Optional[str] = None) -> Any:
    """Replace the long ``#doc=`` links of a tool result by short ``#d=<id>`` links to documents kept in ``store``
    (assistants retype links into their replies, and long payloads do not survive that). With ``pdf_base``,
    ``pdf_url`` is ``<pdf_base><id>``, the PDF served by :func:`_add_pdf_route`: a plain link that does not depend
    on the editor running in the browser, and that cannot be mistaken for ``viewer_url``."""
    from .llm.link import document_from_link

    if not (isinstance(result, dict) and "viewer_url" in result):
        return result
    id_ = store.put(document_from_link(result["viewer_url"]))
    if id_ is None:
        return result
    url = f"{base}#d={id_}"
    return {**result, "viewer_url": url, "pdf_url": f"{pdf_base}{id_}" if pdf_base else url + "&download=pdf"}


def _pdf_base(link_base: str) -> Optional[str]:
    """PDF link prefix next to the editor: ``https://uniwire.sh/viewer/`` -> ``https://uniwire.sh/pdf/``."""
    head, sep, _ = link_base.rpartition("/viewer/")
    return f"{head}/pdf/" if sep else None


def _guard(fn, tool_error, pool=None, store=None, link_base: str = "", pdf_base: Optional[str] = None):
    """Report anticipated failures (bad document, unknown type...) as tool errors the model can read.
    With a worker ``pool`` (public mode), document tools run in a child process and any failure becomes a short
    tool error (no stack trace). With a document ``store``, the links of the results are short ones."""
    from .resolve import UniwireError

    sig = inspect.signature(fn)
    pooled = pool is not None and fn.__name__ in POOLED

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        status = "error"
        try:
            if pooled:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                result = pool.call(fn.__name__, dict(bound.arguments))
            else:
                result = fn(*args, **kwargs)
            result = _shorten(result, store, link_base, pdf_base) if store is not None else result
            status = "ok"
            return result
        except (T.ToolError, UniwireError, KeyError, FileNotFoundError, json.JSONDecodeError) as e:
            raise tool_error(str(e)) from None
        except Exception as e:
            if pool is None:  # local use: unchanged behaviour
                raise
            raise tool_error(f"internal error ({type(e).__name__})") from None
        finally:
            # usage log: tool, outcome, duration; nothing about the caller (no address) or the document
            log.info("tool=%s status=%s ms=%d", fn.__name__, status, (time.monotonic() - t0) * 1000)
    return wrapper


def build_server(pool=None, store=None, link_base: Optional[str] = None, pdf_base: Optional[str] = None):
    """Create the MCP server with every tool, resource and prompt registered. ``pool``: a
    :class:`~uniwire.llm.sandbox.WorkerPool` that runs the document tools (public mode). ``store``: a
    :class:`~uniwire.llm.store.DocStore` for short editor links (``link_base``: the editor URL)."""
    from .llm.link import VIEWER_URL

    link_base = link_base or VIEWER_URL
    cls, tool_error = _sdk()
    try:
        from mcp.types import Icon

        identity: dict[str, Any] = {"title": "uniwire", "website_url": WEBSITE_URL,
                                    "icons": [Icon(src=ICON_URL, mime_type="image/png", sizes=["512x512"])]}
    except ImportError:  # SDK without icons
        identity = {}
    try:
        server = cls("uniwire", instructions=INSTRUCTIONS, version=__version__, **identity)
    except TypeError:
        try:
            server = cls("uniwire", instructions=INSTRUCTIONS, version=__version__)
        except TypeError:
            server = cls("uniwire", instructions=INSTRUCTIONS)

    try:
        from mcp.types import ToolAnnotations
    except ImportError:  # very old SDK
        ToolAnnotations = None  # noqa: N806

    def tool(title: str):
        """Register a tool. Every uniwire tool computes its result from its arguments and reaches no outside system.
        With a document ``store``, the tools whose results carry links (:data:`LINKED`) also publish the document
        for 30 days at a web address anyone with the link can open: a lasting effect outside the conversation, so
        they are neither read-only nor closed-world (same document, same link: idempotent; nothing is overwritten
        or deleted)."""
        def deco(fn):
            kwargs: dict[str, Any] = {"title": title}
            if ToolAnnotations is not None:
                publishes = store is not None and fn.__name__ in LINKED
                kwargs["annotations"] = ToolAnnotations(title=title, read_only_hint=not publishes,
                                                        destructive_hint=False, idempotent_hint=True,
                                                        open_world_hint=publishes)
            try:
                return server.tool(**kwargs)(_guard(fn, tool_error, pool, store, link_base, pdf_base))
            except TypeError:  # mcp 1.x without title / annotations
                return server.tool()(_guard(fn, tool_error, pool, store, link_base, pdf_base))
        return deco

    @tool("Reference card of the uniwire format")
    def get_reference_card(level: str = "compact", lang: str = "en") -> str:
        """Reference card of the uniwire format for electrical diagrams: document skeleton, node types (breakers,
        RCDs, cables, loads, transformers, PV...) and fields, enums, links, pitfalls, examples. Read it before writing
        a document. level: 'compact' (~3k tokens) or 'full'; lang: 'en' or 'fr'."""
        return T.get_reference_card(level, lang)

    @tool("List the node types")
    def list_types(category: Optional[str] = None, lang: str = "en") -> list[dict[str, str]]:
        """List node types (type, category, label), optionally for one category: source, measure,
        protection, switching, control, converter, conductor, container, connector, load."""
        return T.list_types(category, lang)

    @tool("Fields of a node type")
    def type_info(type: str, lang: str = "en") -> dict[str, Any]:  # noqa: A002
        """All fields of a node type with descriptions and allowed values (enums)."""
        return T.type_info(type, lang)

    @tool("Validate an electrical diagram")
    def validate(document: Document) -> dict[str, Any]:
        """Validate a uniwire document (electrical diagram as JSON: object, JSON text or file path) against the
        format. Returns valid + issues, each naming the node id and field when possible, plus viewer_url and pdf_url
        (links for the user). check does the same and also applies the electrical rules."""
        return T.validate(document)

    @tool("Check an electrical installation (NF C 15-100, IEC 60364)")
    def check(document: Document, profiles: Optional[list[str]] = None) -> dict[str, Any]:
        """Check an electrical installation (single-line diagram, panel, schéma unifilaire, tableau électrique):
        validates the document, then applies the rule profiles (NF C 15-100 'nfc15100', IEC 60364 'iec60364', PLC;
        default: the document's 'profiles'; 'core' always applies): breaker ratings against cable sections, RCDs,
        circuits per protection, selectivity...
        Returns findings (level error/warning/info, rule, node id, message, source), a summary, viewer_url (opens
        the document in the uniwire web editor: drawing, findings, downloads) and pdf_url (the PDF drawn by
        uniwire). Give both to the user as clickable links. 'scope' says what the checks cover: tell the
        user once that they are not a conformity certificate."""
        return T.check(document, profiles)

    @tool("Outline of an electrical diagram")
    def describe(document: Document, lang: str = "en") -> str:
        """Text outline of an electrical diagram: installation, full tree of the panel with stable ids, ratings
        and cables, links, interlocks, boards and findings summary. Use it to review a document or find the ids for
        apply_patch."""
        return T.describe(document, lang)

    @tool("Edit an electrical diagram")
    def apply_patch(document: Document, ops: Union[list[dict[str, Any]], str], validate: bool = True) -> dict[str, Any]:
        """Edit an electrical diagram by node id (change a rating, add a circuit, move a load...) and return the
        new document. ops (applied in order):
        {"op":"set","id":ID,"path":"in_A","value":20} (null value removes; no id = document root, e.g.
        path "installation.earthing"); {"op":"add","parent":ID,"node":{...},"index":0} (or "at":"sources");
        {"op":"remove","id":ID}; {"op":"move","id":ID,"parent":ID,"index":0};
        {"op":"rename","id":ID,"new_id":NEW}; {"op":"link","link":{"kind":"control","from":ID,"to":ID}};
        {"op":"unlink","id":LINK_ID} or {"op":"unlink","from":ID,"to":ID,"kind":K}.
        On failure returns ok=false and errors naming the failing op index (null = validation of the result)."""
        return T.apply_patch(document, ops, validate)

    @tool("Draw the single-line or multi-line diagram")
    def render(document: Document, kind: str = "single-line", format: str = "svg",  # noqa: A002
               sheet: Optional[int] = None, view: Optional[str] = None, path: Optional[str] = None,
               color: Optional[str] = None, conductor_colors: Optional[str] = None) -> dict[str, Any]:
        """Draw the electrical diagram (schéma unifilaire / multifilaire). kind: 'single-line' or 'multi-line';
        view: a view id of the document (e.g. a
        wire-marking view). format 'svg' returns the SVG text of every sheet (or of 'sheet', numbered from 1);
        'pdf' writes to 'path' if given, else returns base64 (requires the uniwire[pdf] extra); on the hosted
        server it returns pdf_url instead. To give the user the PDF, give them pdf_url as a clickable link.
        color: 'none' | 'conductors' | 'phase' | 'source' | 'status' | 'voltage' (adds a legend);
        conductor_colors: 'iec' (IEC 60445) | 'us'."""
        return T.render(document, kind, format, sheet, view, path, color, conductor_colors)

    @tool("Links to open the diagram and its PDF")
    def viewer_link(document: Document) -> dict[str, Any]:
        """Links for the user: viewer_url opens the document in the uniwire web editor (drawing, single-line and
        multi-line, rule findings, PDF and SVG downloads, nothing to install); pdf_url gives the PDF drawn by
        uniwire. On the hosted server the document is kept 30 days so that the short links open it
        (anyone with a link can open it); elsewhere it travels in the link (after '#') and is stored nowhere. Give
        them to the user as clickable Markdown links."""
        return T.viewer_link(document)

    @tool("Wire list, wire markers and cable schedule")
    def wiring(document: Document, what: str = "markers", view: Optional[str] = None) -> dict[str, Any]:
        """Wiring exports of an installation as rows with stable column names (repérage des fils, carnet de
        câbles): what='markers' (one row per wire end, for label
        printers), 'wires' (wire list) or 'cables' (cable schedule). Marks follow the wire_marking rules of
        the view (id), by default the first view that declares them."""
        return T.wiring(document, what, view)

    @tool("Bill of materials")
    def bom(document: Document) -> list[dict[str, Any]]:
        """Bill of materials of an electrical installation (nomenclature), grouped by manufacturer / part number
        (nodes with a product reference)."""
        return T.bom(document)

    @tool("List the example installations")
    def list_examples() -> list[dict[str, Any]]:
        """List the 52 example installations (dwellings, shops, offices, workshops, PV, EV charging, UPS, MV/LV
        substations, PLCs): name, title, language, profiles, earthing, system. Good starting points."""
        return T.list_examples()

    @tool("Get an example installation")
    def get_example(name: str) -> dict[str, Any]:
        """Return an example installation document by name (or number prefix, e.g. '02'), to adapt to the
        user's project."""
        return T.get_example(name)

    @tool("Normalized document")
    def normalize(document: Document) -> dict[str, Any]:
        """Resolved document: templates applied, every id assigned, canonical numbers."""
        return T.normalize(document)

    @server.resource("uniwire://schema", name="schema", mime_type="application/schema+json",
                     description="JSON Schema (draft 2020-12) of the uniwire format")
    def schema_resource() -> str:
        return json.dumps(T.schema(), ensure_ascii=False, indent=1)

    @server.resource("uniwire://card", name="card", mime_type="text/markdown",
                     description="Compact reference card of the uniwire format")
    def card_resource() -> str:
        return T.get_reference_card("compact", "en")

    @server.resource("uniwire://card/full", name="card-full", mime_type="text/markdown",
                     description="Full reference card of the uniwire format")
    def card_full_resource() -> str:
        return T.get_reference_card("full", "en")

    @server.prompt(name="design_single_line", description="Guide the design of a single-line diagram: gather "
                   "earthing, supply and loads, write the document, validate, check, fix, render")
    def design_single_line(brief: str = "(ask the user)") -> str:
        return DESIGN_PROMPT.format(brief=brief)

    return server


PUBLIC_HELP = f"""public mode (--public) limits, per tool call:
  document     at most {T.MAX_DOCUMENT_CHARS:,} characters of JSON, {T.MAX_NODES} nodes (after templates,
               devices included); no file paths, no 'path' output
  render       at most {T.MAX_SHEETS} sheets and {T.MAX_OUTPUT_BYTES:,} bytes of output (SVG or PDF)
  apply_patch  at most {T.MAX_PATCH_OPS} operations; the patched document obeys the document limits
  execution    document tools run in --workers child processes (the concurrency limit), killed and
               replaced after --timeout seconds; on Linux each worker is limited to --memory-mb of
               address space and to a CPU-time budget per call
  HTTP         request bodies over {MAX_REQUEST_BODY_BYTES:,} bytes are refused (413) before parsing;
               GET /healthz answers 200 "ok"; with --store, GET /doc/<id> serves the stored documents
               and GET /pdf/<id> their PDF (drawn in a worker process)
Local use (stdio or HTTP without --public) has none of these limits and runs in-process."""


def _http_supported() -> bool:
    """True if the installed MCP SDK has what the HTTP transport needs (mcp >= 2: transport security,
    streamable HTTP options, request body limit)."""
    try:
        from mcp.server.transport_security import TransportSecuritySettings  # noqa: F401
    except ImportError:
        return False
    cls, _ = _sdk()
    run_http = getattr(cls, "run_streamable_http_async", None)
    if run_http is None:
        return False
    params = inspect.signature(run_http).parameters
    return all(p in params for p in ("transport_security", "stateless_http", "json_response",
                                     "streamable_http_path", "max_request_body_size"))


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import os

    from .llm import sandbox

    ap = argparse.ArgumentParser(prog="uniwire-mcp", description="uniwire MCP server (stdio by default)",
                                 epilog=PUBLIC_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--http", action="store_true", help="serve MCP over streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--path", default="/mcp", help="HTTP endpoint path")
    ap.add_argument("--public", action="store_true",
                    help="hosted mode: no file system access, bounded documents and outputs, document tools run "
                    "in worker processes with a timeout, stateless JSON responses (limits below)")
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="Host header accepted over HTTP (repeat; e.g. mcp.example.org)")
    ap.add_argument("--workers", type=int, default=sandbox.WORKERS,
                    help=f"public mode: worker processes = concurrent document tool calls (default {sandbox.WORKERS})")
    ap.add_argument("--timeout", type=float, default=sandbox.TIMEOUT_S,
                    help=f"public mode: seconds per tool call before the worker is killed (default {sandbox.TIMEOUT_S:g})")
    ap.add_argument("--store", metavar="DIR",
                    help="keep the documents of the tool results in DIR for 30 days and return short editor links "
                    "(#d=<id>, served at GET /doc/<id>) instead of long #doc= links")
    ap.add_argument("--link-base", default=None,
                    help="editor URL used in the links (default https://uniwire.sh/viewer/)")
    ap.add_argument("--pdf-base", default=None,
                    help="with --store: prefix of the PDF links, proxied to GET /pdf/<id> (default: the editor URL "
                    "with /viewer/ replaced by /pdf/)")
    ap.add_argument("--memory-mb", type=int, default=sandbox.MEMORY_BYTES // (1024 * 1024),
                    help="public mode, Linux: address space limit of each worker in MB "
                    f"(default {sandbox.MEMORY_BYTES // (1024 * 1024)}; 0 = none)")
    a = ap.parse_args(argv)
    if a.public:
        os.environ["UNIWIRE_MCP_PUBLIC"] = "1"
        T.PUBLIC = True
    try:
        _sdk()
    except ImportError:
        print("uniwire-mcp needs the MCP SDK: pip install 'uniwire[mcp]'", file=sys.stderr)
        return 1
    if a.http and not _http_supported():
        print("uniwire-mcp --http needs the MCP SDK 2.x (transport security and streamable HTTP options): "
              "pip install -U 'mcp>=2.0'", file=sys.stderr)
        return 1
    pool = None
    if a.public:
        pool = sandbox.WorkerPool(a.workers, a.timeout, a.memory_mb * 1024 * 1024 or None)
    try:
        store = None
        if a.store:
            from .llm.store import DocStore

            store = DocStore(a.store)
        from .llm.link import VIEWER_URL

        # PDF links only where GET /pdf/<id> is served (HTTP with a store)
        pdf_base = (a.pdf_base or _pdf_base(a.link_base or VIEWER_URL)) if a.http and store is not None else None
        server = build_server(pool, store, a.link_base, pdf_base)
        if not a.http:
            server.run()  # stdio transport
            return 0
        from mcp.server.transport_security import TransportSecuritySettings

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
        hosts = a.allowed_host or ["127.0.0.1", "localhost"]
        hosts = hosts + [f"{h}:{a.port}" for h in hosts if ":" not in h]
        security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                             allowed_origins=[f"https://{h}" for h in a.allowed_host])
        extra: dict[str, Any] = {}
        if a.public:
            extra["max_request_body_size"] = MAX_REQUEST_BODY_BYTES
            _add_healthz(server)
            _add_icon_route(server)
        if store is not None:
            _add_doc_route(server, store)
            _add_pdf_route(server, store, pool)
        server.run("streamable-http", host=a.host, port=a.port, streamable_http_path=a.path,
                   stateless_http=True, json_response=True, transport_security=security, **extra)
        return 0
    finally:
        if pool is not None:
            pool.close()


def _add_healthz(server) -> None:
    """``GET /healthz`` -> 200 "ok" (container health checks; no MCP session, no document processing)."""
    from starlette.responses import PlainTextResponse

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(request):  # noqa: ARG001
        return PlainTextResponse("ok")


def _add_icon_route(server) -> None:
    """``GET /favicon.ico`` -> redirect to the icon (clients that look for the favicon of the server's host)."""
    from starlette.responses import RedirectResponse

    @server.custom_route("/favicon.ico", methods=["GET"], include_in_schema=False)
    async def favicon(request):  # noqa: ARG001
        return RedirectResponse(ICON_URL, status_code=302)


def _add_pdf_route(server, store, pool) -> None:
    """``GET /pdf/<id>`` -> the PDF of a stored document, drawn by the library (in a worker process with
    ``pool``), shown inline with the document title as file name; 404 when unknown or expired."""
    import base64

    from starlette.concurrency import run_in_threadpool
    from starlette.responses import PlainTextResponse, Response

    headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "X-Content-Type-Options": "nosniff"}

    def make(text: str) -> dict[str, Any]:
        return pool.call("pdf_file", {"document": text}) if pool is not None else T.pdf_file(text)

    @server.custom_route("/pdf/{doc_id}", methods=["GET"], include_in_schema=False)
    async def get_pdf(request):
        text = store.get(request.path_params["doc_id"])
        if text is None:
            return PlainTextResponse("unknown or expired document", status_code=404, headers=headers)
        t0 = time.monotonic()
        try:
            r = await run_in_threadpool(make, text)
        except Exception as e:  # noqa: BLE001  (worker errors and timeouts: a short message, no stack trace)
            log.info("route=pdf status=error ms=%d", (time.monotonic() - t0) * 1000)
            return PlainTextResponse(f"cannot draw this document: {e}", status_code=422, headers=headers)
        log.info("route=pdf status=ok ms=%d", (time.monotonic() - t0) * 1000)
        disp = f'inline; filename="{r["filename"]}"'
        return Response(base64.b64decode(r["pdf_base64"]), media_type="application/pdf",
                        headers={**headers, "Content-Disposition": disp})


def _add_doc_route(server, store) -> None:
    """``GET /doc/<id>`` -> the stored document text (JSON), 404 when unknown or expired."""
    from starlette.responses import PlainTextResponse, Response

    headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "X-Content-Type-Options": "nosniff"}

    @server.custom_route("/doc/{doc_id}", methods=["GET"], include_in_schema=False)
    async def get_doc(request):
        text = store.get(request.path_params["doc_id"])
        if text is None:
            return PlainTextResponse("not found (links expire 30 days after their last use)", 404, headers=headers)
        return Response(text, media_type="application/json", headers=headers)


if __name__ == "__main__":
    sys.exit(main())
