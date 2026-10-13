# uniwire-data-iec81346

IEC 81346-2:2019 component classes (1-, 2- and 3-letter codes) as JSON, for the
[uniwire](https://github.com/uniwire-dev/uniwire) registry: `pip install uniwire-data-iec81346`, then
`uniwire.registry.iec81346_table()` returns the table.

## Licence: CC BY-SA 4.0

This package contains **data only** and is licensed under Creative Commons Attribution-ShareAlike 4.0
International (<https://creativecommons.org/licenses/by-sa/4.0/>, full text in `LICENSE`), unlike the Apache-2.0 `uniwire`
package. It is a separate distribution so that the share-alike terms stay with the data.

- Attribution: "Data from the Wikipedia article *IEC 81346* (<https://en.wikipedia.org/wiki/IEC_81346>),
  revision 1378915541 of 2026-10-06, retrieved 2026-10-11, by Wikipedia contributors, CC BY-SA 4.0."
  The table comes from the Czech CCI classification (Agentura ČAS).
- Changes: converted to JSON (code, level, parent); a description built from the parent headings was
  added; one row with an invalid code was removed (listed in `header.anomalies`).
- Share-alike: this file and anything derived from it must stay under CC BY-SA 4.0 with the same
  attribution. Code that *reads* the file is not a derivative work.
- The headings follow the CCI classification and may differ slightly from the text of
  IEC 81346-2:2019, which is authoritative.
