"""Registry of component types (metadata: category, IEC 81346 letter code,
labels, default symbol, CIM / IFC / IEC 61850 SCL mappings)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any


@cache
def registry() -> dict[str, Any]:
    return json.loads(resources.files(__package__).joinpath("core.json").read_text("utf-8"))


def info(type_: str) -> dict[str, Any]:
    return registry()["types"][type_]


def category(type_: str) -> str:
    return info(type_)["category"]


def label(type_: str, lang: str | None = None) -> str:
    """Human label of a type, in ``lang`` (default: the render / environment language)."""
    from ..i18n import render_lang

    labels = info(type_)["label"]
    lang = lang or render_lang()
    return labels.get(lang) or labels["en"]


def is_load(type_: str) -> bool:
    return category(type_) == "load"


def _data(name: str) -> dict[str, Any]:
    return json.loads(resources.files(__package__).joinpath("data", name).read_text("utf-8"))


@cache
def _iec81346_data() -> dict[str, Any] | None:
    try:
        import uniwire_data_iec81346
    except ImportError:
        return None
    return uniwire_data_iec81346.load()


def iec81346_table() -> dict[str, dict[str, Any]]:
    """IEC 81346-2:2019 classes (1-, 2- or 3-letter codes) indexed by code.

    The data (from Wikipedia, CC BY-SA 4.0) ships in the optional ``uniwire-data-iec81346``
    package; without it the table is empty. Header (sources, licence, date): :func:`iec81346_header`.
    """
    data = _iec81346_data()
    return {c["code"]: c for c in data["classes"]} if data else {}


def iec81346_header() -> dict[str, Any] | None:
    data = _iec81346_data()
    return data["header"] if data else None


def iec81346_class(type_: str) -> str | None:
    """IEC 81346-2 class (2 or 3 letters) of a registry type, or ``None``."""
    return info(type_).get("iec81346_class")


@cache
def iz_tables() -> dict[str, Any]:
    """Current-carrying capacities (GUIA-BT-19 / UNE 20460-5-523:2004), see ``data/iz_tables.json``. No longer used
    by the rules (see ``iz_iec60364``), kept for the code reading it."""
    return _data("iz_tables.json")


@cache
def iz_iec60364() -> dict[str, Any]:
    """Current-carrying capacities at the reference conditions of IEC 60364-5-52, as formulas, see
    ``data/iz_iec60364.json``."""
    return _data("iz_iec60364.json")
