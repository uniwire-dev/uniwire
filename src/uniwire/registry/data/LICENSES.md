# Licences of the data files

uniwire code is licensed under Apache-2.0 (see `LICENSE`). This folder holds third-party data; each
file keeps its own terms.

| File | Origin | Licence |
|---|---|---|
| `iz_iec60364.json` | Coefficients of formulas computed by the project after IEC 60364-5-52 (no table reproduced) | Apache-2.0, as the code. |
| `iz_tables.json` | Numerical values read from the official Spanish guide GUIA-BT-19 (Ministerio de Industria, Feb. 2009, rev. 2), tables A and D, taken from UNE 20460-5-523:2004. No longer used by the rules, kept for the code reading it. | Factual values cited with their source. No third-party licence declared. |

The IEC 81346-2:2019 class table (Wikipedia, CC BY-SA 4.0) is **not** in this package: it ships
separately as `uniwire-data-iec81346` (`packages/uniwire-data-iec81346`) so that its share-alike terms
stay with the data. The `iec81346_class` field of `core.json` only refers to a code of that table,
chosen by the project; it does not reproduce the table.

## `iz_iec60364.json`

- Formulas `a * S^m` per installation method, insulation, material and number of loaded conductors, for two
  ranges of sections, computed by the project and never above the values of IEC 60364-5-52. It does not replace
  the standard or a national one.
- `factors`: the grouping, soil resistivity and third-harmonic correction factors, as formulas with a few
  coefficients each, computed by the project the same way.

## `iz_tables.json`

- Current-carrying capacities are technical data, reproduced with their source (document, page,
  table) in the file header.
- Values are given for 40 °C ambient, the Spanish reference. They do not replace IEC 60364-5-52 or
  NF C 15-100.
