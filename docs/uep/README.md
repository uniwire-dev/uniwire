# uniwire Enhancement Proposals (UEP)

Every change to the uniwire format (the [specification](../SPEC.md), the JSON Schema and the type registry) goes
through a short public proposal: a **UEP**. This page recalls the process and lists the proposals.

## Process

1. **Open an issue** with the **Format proposal** template (label `uep`). Describe the use case: which real
   installations or drawings need the change. If you can, attach a small anonymised example.
2. **Write the proposal.** Larger proposals are also written as a document in this folder
   (`docs/uep/NNNN-short-title.md`). Use these sections:
   * **Motivation**: use cases, and what the current format cannot express.
   * **Goals and non-goals.**
   * **Proposal**: fields, types or link kinds, with JSON examples, and the mapping to CIM / IFC / IEC 61850 SCL
     where relevant.
   * **Compatibility**: minor versions (1.x) only add optional fields, types or enumeration values. Anything that
     breaks existing files waits for the next major version and ships with a migration function.
   * **Implementation**: the change in the reference library, the regenerated schema, the specification updated, the changelog entry, at least one example or test that uses it, and the whole test suite
     green.
   * **Open questions.**
3. **Discuss** on the issue and the pull request. The proposal changes status as it moves on.
4. **Implement** once the proposal is accepted. The specification, not the UEP, is the normative reference after
   the change is released.

The full rules are in [Contributing](../contributing.md#changing-the-format-uniwire-enhancement-proposals-uep).

### Statuses

| Status | Meaning |
|---|---|
| Draft | Open for discussion. Anything can change |
| Accepted | Agreed. Implementation can start, details may still move |
| Final | Implemented and released. The specification holds the normative text |
| Rejected / Withdrawn | Not pursued. Kept for the record |
| Superseded | Replaced by a later UEP |

## Index

| UEP | Title | Status | Target |
|---|---|---|---|
| [0001](0001-terminals-and-wires.md) | Terminals, terminal strips and wires | Draft | 2.0 |
