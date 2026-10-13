"""uniwire data model (pydantic v2 is the source of truth for the JSON Schema)."""

from .base import Cable, Installation, Meta, Revision, UWModel
from .document import (
    DEFAULT_CARTOUCHE,
    FORMAT_VERSION,
    SCHEMA_ID,
    Document,
    Enclosure,
    Interlock,
    Link,
    Override,
    View,
    WireMarking,
)
from .nodes import NODE_CLASSES, NODE_TYPES, Node, NodeBase

__all__ = [
    "Cable", "Installation", "Meta", "Revision", "UWModel",
    "DEFAULT_CARTOUCHE", "FORMAT_VERSION", "SCHEMA_ID", "Document", "Enclosure", "Interlock", "Link", "Override", "View", "WireMarking",
    "NODE_CLASSES", "NODE_TYPES", "Node", "NodeBase",
]
