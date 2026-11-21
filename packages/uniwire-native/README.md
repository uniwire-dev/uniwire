# uniwire-native

Optional compiled part of [uniwire](https://uniwire.sh): the search of the grid link router (the costs of each grid
move and the cheapest-route search over them), written in Rust. uniwire uses it when it is installed and draws
exactly the same drawings without it, in pure Python, only slower on large drawings.

```
pip install "uniwire[native]"
```

The module does no layout of its own: uniwire builds the grid, the obstacles and the costs of each grid line and
passes them as flat arrays; the module runs the same search, with the same floating-point operations in the same
order and the same tie order, and returns the route. Set `UNIWIRE_NATIVE=0` to use the pure Python search even when
the module is installed (to compare the two).

Build from source (Rust and [maturin](https://www.maturin.rs/)): `pip install ./packages/uniwire-native`.

## In the web editor

The web editor runs uniwire in the browser with [Pyodide](https://pyodide.org) and loads this module too, built for
the Pyodide release it pins (`PYODIDE_VERSION` in `viewer/worker.js`):

```
packages/uniwire-native/build-pyodide.sh            # -> packages/uniwire-native/target/pyodide/*_wasm32.whl
python viewer/build.py --native packages/uniwire-native/target/pyodide
```

The script reads with `pyodide-build` the Emscripten and Rust versions of that release, installs them in user space
(the Emscripten SDK in the `pyodide-build` cache, the Rust nightly and its `wasm32-unknown-emscripten` target with
rustup) and builds the wheel with maturin. `node packages/uniwire-native/pyodide-check.mjs <uniwire wheel> <this
wheel> examples` (after `npm install pyodide@<that release>`) checks in Pyodide that the module is used and draws
every bundled example as the pure Python search does. If the editor cannot load the module, it draws in pure Python.

Apache-2.0, like uniwire.
