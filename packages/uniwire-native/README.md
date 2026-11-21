# uniwire-native

Optional compiled part of [uniwire](https://uniwire.sh): the search of the grid link router (the costs of each grid
move and the cheapest-route search over them), written in Rust. uniwire uses it when it is installed and draws
exactly the same drawings without it, in pure Python (as in the browser editor), only slower on large documents.

```
pip install "uniwire[native]"
```

The module does no layout of its own: uniwire builds the grid, the obstacles and the costs of each grid line and
passes them as flat arrays; the module runs the same search, with the same floating-point operations in the same
order and the same tie order, and returns the route. Set `UNIWIRE_NATIVE=0` to use the pure Python search even when
the module is installed (to compare the two).

Build from source (Rust and [maturin](https://www.maturin.rs/)): `pip install ./packages/uniwire-native`.

Apache-2.0, like uniwire.
