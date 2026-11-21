"""The editor's build script (viewer/build.py): the optional compiled link router served with the site."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("viewer_build", Path(__file__).parent.parent / "viewer" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

WASM = "uniwire_native-0.1.0-cp310-abi3-emscripten_3_1_58_wasm32.whl"


def test_native_wheel_from_a_directory_or_a_file(tmp_path):
    (tmp_path / "uniwire_native-0.1.0-cp310-abi3-macosx_11_0_arm64.whl").write_bytes(b"")  # not for the browser
    (tmp_path / WASM).write_bytes(b"")
    assert build.native_wheel(tmp_path).name == WASM
    assert build.native_wheel(tmp_path / WASM).name == WASM


def test_a_wheel_not_built_for_the_browser_is_refused(tmp_path):
    other = tmp_path / "uniwire_native-0.1.0-cp310-abi3-macosx_11_0_arm64.whl"
    other.write_bytes(b"")
    with pytest.raises(SystemExit):
        build.native_wheel(other)
    with pytest.raises(SystemExit):
        build.native_wheel(tmp_path)  # no wasm32 wheel in it


def test_copy_native_replaces_the_previous_build(tmp_path, monkeypatch):
    dist, src = tmp_path / "dist", tmp_path / "src"
    dist.mkdir()
    src.mkdir()
    monkeypatch.setattr(build, "DIST", dist)
    (dist / "uniwire_native-0.0.9-cp310-abi3-emscripten_3_1_58_wasm32.whl").write_bytes(b"old")
    (dist / "uniwire-1.0.0-py3-none-any.whl").write_bytes(b"lib")
    (src / WASM).write_bytes(b"new")
    assert build.copy_native(src) == dist / WASM
    assert sorted(p.name for p in dist.iterdir()) == sorted(["uniwire-1.0.0-py3-none-any.whl", WASM])
    assert build.copy_native(None) is None  # built without it: none served
    assert [p.name for p in dist.iterdir()] == ["uniwire-1.0.0-py3-none-any.whl"]
