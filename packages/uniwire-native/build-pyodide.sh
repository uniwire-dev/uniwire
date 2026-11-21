#!/usr/bin/env bash
# Builds uniwire-native for the web editor: a wheel for the Pyodide release pinned in viewer/worker.js
# (PYODIDE_VERSION), with the Emscripten SDK and the Rust nightly that this release is built with.
#
#   packages/uniwire-native/build-pyodide.sh [OUT_DIR]        (default: packages/uniwire-native/target/pyodide)
#   python viewer/build.py --native packages/uniwire-native/target/pyodide
#
# Needs Python 3.12 or later (PYTHON, default python3.12), rustup and network access. Installs into user space only:
# the Pyodide cross-build environment and its Emscripten SDK in the pyodide-build cache, the Rust toolchain with
# rustup, the build tools in virtual environments under packages/uniwire-native/target/.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out=${1:-$here/target/pyodide}
python=${PYTHON:-python3.12}
tools=$here/target/pyodide-tools
pyodide_version=$(sed -n 's/^const PYODIDE_VERSION = "\(.*\)";.*/\1/p' "$root/viewer/worker.js")
[ -n "$pyodide_version" ] || { echo "PYODIDE_VERSION not found in viewer/worker.js" >&2; exit 1; }

# pyodide-build gives the versions of this Pyodide release and installs its Emscripten SDK.
[ -x "$tools/pyodide-build/bin/pyodide" ] || {
  "$python" -m venv "$tools/pyodide-build"
  "$tools/pyodide-build/bin/python" -m pip install -q "pyodide-build==0.39.4"
}
pyodide() { "$tools/pyodide-build/bin/pyodide" "$@"; }
pyodide xbuildenv install "$pyodide_version"
pyodide xbuildenv install-emscripten
emscripten_version=$(pyodide config get emscripten_version)
emsdk=$(cd "$(pyodide config get emscripten_dir)/../.." && pwd)
toolchain=$(pyodide config get rust_toolchain)
rustflags="$(pyodide config get rustflags) -Z link-native-libraries=no"
python_version=$(pyodide config get python_version | cut -d. -f1-2)

rustup toolchain install "$toolchain" --profile minimal --target wasm32-unknown-emscripten --no-self-update
[ -x "$tools/maturin/bin/maturin" ] || {
  "$python" -m venv "$tools/maturin"
  "$tools/maturin/bin/python" -m pip install -q "maturin>=1.7,<2"
}
# shellcheck disable=SC1091
source "$emsdk/emsdk_env.sh" > /dev/null 2>&1
mkdir -p "$out"
rm -f "$out"/uniwire_native-*_wasm32.whl
# The pyodide command is kept off the PATH: maturin then tags the wheel emscripten_<version>_wasm32, the tag this
# Pyodide release installs (with it, maturin writes the newer pyemscripten tag, which Pyodide 0.27 refuses).
RUSTUP_TOOLCHAIN=$toolchain RUSTFLAGS=$rustflags "$tools/maturin/bin/maturin" build --release --locked \
  --target wasm32-unknown-emscripten -i "python$python_version" --out "$out" -m "$here/Cargo.toml"
wheel=$(ls "$out"/uniwire_native-*-emscripten_"${emscripten_version//./_}"_wasm32.whl 2> /dev/null || true)
[ -n "$wheel" ] || { echo "no wheel tagged emscripten_${emscripten_version//./_}_wasm32 in $out" >&2; exit 1; }
echo "Pyodide $pyodide_version (Emscripten $emscripten_version, Rust $toolchain): $wheel"
