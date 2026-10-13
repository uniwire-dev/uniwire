# Licences of the data files

uniwire code is licensed under Apache-2.0 (see `LICENSE`). This folder holds third-party data; each
file keeps its own terms.

| File | Origin | Licence |
|---|---|---|
| `iz_tables.json` | Numerical values read from the official Spanish guide GUIA-BT-19 (Ministerio de Industria, Feb. 2009, rev. 2), tables A and D, taken from UNE 20460-5-523:2004 | Factual values cited with their source. No third-party licence declared. |

The IEC 81346-2:2019 class table (Wikipedia, CC BY-SA 4.0) is **not** in this package: it ships
separately as `uniwire-data-iec81346` (`packages/uniwire-data-iec81346`) so that its share-alike terms
stay with the data. The `iec81346_class` field of `core.json` only refers to a code of that table,
chosen by the project; it does not reproduce the table.

## `iz_tables.json`

- Current-carrying capacities are technical data, reproduced with their source (document, page,
  table) in the file header.
- Values are given for 40 °C ambient, the Spanish reference. They do not replace IEC 60364-5-52 or
  NF C 15-100.
