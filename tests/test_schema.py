import json

import jsonschema
import pytest

from tests.conftest import ROOT
from uniwire.schema import json_schema

SCHEMA_FILE = ROOT / "schema" / "uniwire.schema.json"


def test_committed_schema_is_up_to_date():
    committed = json.loads(SCHEMA_FILE.read_text("utf-8"))
    assert committed == json_schema(), "outdated schema: run `uniwire schema -o schema/uniwire.schema.json`"


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA_FILE.read_text("utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_schema_rejects_typos(validator):
    bad = {"sources": [{"type": "grid", "children": [{"type": "breaker", "calibre": 16}]}]}
    assert any("calibre" in e.message for e in validator.iter_errors(bad))
