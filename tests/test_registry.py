import json
from pathlib import Path

import pytest

from uniwire import registry

needs_iec81346 = pytest.mark.skipif(registry.iec81346_header() is None,
                                    reason="optional uniwire-data-iec81346 package not installed")

ROOT = Path(__file__).resolve().parent.parent


@needs_iec81346
def test_iec81346_table_loader():
    t = registry.iec81346_table()
    assert t["QAB"]["en"] == "Circuit breaker" and t["QAB"]["parent"] == "QA" and t["QAB"]["level"] == 3
    assert t["QA"]["parent"] == "Q" and t["Q"]["parent"] is None
    assert sum(1 for c in t.values() if c["level"] == 1) == 17
    for c in t.values():
        assert len(c["code"]) == c["level"]
        if c["parent"]:
            assert c["parent"] in t and c["code"].startswith(c["parent"])
    h = registry.iec81346_header()
    assert h["licence"]["id"] == "CC-BY-SA-4.0" and h["retrieved"] == "2026-10-11"


@needs_iec81346
def test_registry_classes_exist_in_table():
    t = registry.iec81346_table()
    for name, info in registry.registry()["types"].items():
        assert "iec81346_class" in info, name
        cls = info["iec81346_class"]
        if cls is not None:
            assert cls in t and len(cls) in (2, 3), (name, cls)
    assert registry.iec81346_class("breaker") == "QAB"
    assert registry.iec81346_class("rcd") == "FBA"


def test_iz_tables():
    iz = registry.iz_tables()
    assert iz["header"]["reference_conditions"]["air"]["ambient_C"] == 40
    cu = iz["tables"]["Cu"]
    for ins in ("PVC", "XLPE"):
        for m in ("A1", "A2", "B1", "B2", "C", "E", "F"):
            for n in ("2", "3"):
                col = cu[ins][m][n]
                assert set(col) == {f"{s:g}" for s in (1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300)}
                vals = [v for v in col.values() if v is not None]
                assert vals == sorted(vals)
    assert cu["PVC"]["C"]["2"]["1.5"] == 16.5 and cu["XLPE"]["F"]["2"]["25"] == 140
    assert iz["tables"]["Al"]["XLPE"]["D-duct"]["3"]["300"] == 350


def test_data_files_are_packaged():
    data = ROOT / "src" / "uniwire" / "registry" / "data"
    assert (data / "iz_tables.json").exists() and (data / "LICENSES.md").exists()
    # the CC BY-SA table must stay out of the Apache-2.0 package
    assert not (data / "iec81346_2.json").exists()
    ext = ROOT / "packages" / "uniwire-data-iec81346" / "src" / "uniwire_data_iec81346" / "iec81346_2.json"
    if not ext.exists():  # the source distribution does not ship packages/
        pytest.skip("the data package sources are not available")
    assert json.loads(ext.read_text("utf-8"))["header"]["licence"]
