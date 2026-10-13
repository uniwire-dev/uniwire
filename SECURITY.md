# Security policy

## Supported versions

Security fixes are made on the latest released version of the `uniwire` package and on the `main` branch.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report vulnerabilities privately through GitHub Security Advisories: open the
[Security tab of the repository](https://github.com/uniwire-dev/uniwire/security) and click
**"Report a vulnerability"** (direct link: <https://github.com/uniwire-dev/uniwire/security/advisories/new>).
If you cannot use GitHub, write to <security@uniwire.sh>.

Please include:

* the affected version (`python -c "import uniwire; print(uniwire.__version__)"`);
* a description of the issue and its impact;
* a minimal document or script that reproduces it, if possible.

The maintainers will acknowledge the report, investigate it, and coordinate a fix and a disclosure date
with you. Credit is given in the advisory unless you prefer to stay anonymous.

This private channel can also be used to reach the maintainers about Code of Conduct matters.

## Scope

In scope:

* the `uniwire` Python package: it reads JSON documents and writes SVG, PDF, CSV and JSON files. Relevant
  issues include crashes or excessive resource use on crafted documents, unsafe content in generated SVG,
  PDF or CSV output (for example spreadsheet formula injection), or file access outside what a command was
  asked to read or write;
* the MCP server `uniwire-mcp` (stdio and HTTP), in particular its public mode (`--public`) and the official
  image built from `docker/mcp/Dockerfile`;
* the hosted MCP endpoint <https://mcp.uniwire.sh/mcp>: bypassing its limits (document size, time, memory),
  reading or writing files on the server, or affecting other users' requests. Please do not run load or
  denial-of-service tests against it; a short proof of concept is enough;
* the web viewer (`viewer/`, published at <https://uniwire.sh/viewer/>): script injection through a document
  or a shared link;
* the optional data package `uniwire-data-iec81346`.

uniwire's rule checks are consistency aids and do not replace the applicable electrical standards; an
incorrect rule result is a regular bug, not a security vulnerability.
