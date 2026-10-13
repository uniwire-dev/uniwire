"""IEC 81346-2:2019 component classes for uniwire (data only, CC BY-SA 4.0).

Kept out of the Apache-2.0 ``uniwire`` package because of its share-alike licence.
``uniwire.registry.iec81346_table()`` uses it when it is installed.
"""

import json
from importlib import resources
from typing import Any


def load() -> dict[str, Any]:
    """Return the class table: ``{"header": {...source, licence, attribution...}, "classes": [...]}``."""
    return json.loads(resources.files(__package__).joinpath("iec81346_2.json").read_text("utf-8"))
