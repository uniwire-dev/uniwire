"""Helpers that make uniwire usable by LLM assistants.

* :func:`card`: a reference card of the format, generated from the model, the registry and the rules;
* :func:`describe`: a faithful, deterministic outline of a document (stable ids included);
* :func:`patch`: id-based editing operations, validated, with precise errors;
* :func:`flatten` / :func:`unflatten`: the node tree as a flat table with parent ids;
* :func:`viewer_link`: a link that opens a document in the web editor (drawing, findings, PDF).

The MCP server (``uniwire-mcp``, extra ``uniwire[mcp]``) exposes these helpers as tools.
"""

from .card import card
from .describe import describe
from .link import viewer_link
from .patch import PatchError, flatten, materialize_ids, patch, unflatten

__all__ = ["PatchError", "card", "describe", "flatten", "materialize_ids", "patch", "unflatten", "viewer_link"]
