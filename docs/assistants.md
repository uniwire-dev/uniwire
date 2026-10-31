# uniwire in your assistant

Ask an assistant for an electrical diagram in plain words ("draw the single-line diagram of my flat", "check my
panel against NF C 15-100") and get a checked document, the drawing and the PDF. There are three ways, from
nothing to install to fully local.

## Nothing to install: the hosted server

The hosted MCP server runs the reference library for any assistant that supports remote MCP servers:

```text
https://mcp.uniwire.sh/mcp
```

Streamable HTTP, no account, no authentication. It is listed in the
[official MCP registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.uniwire-dev/uniwire)
as `io.github.uniwire-dev/uniwire`, so clients that browse the registry find it by name. Its tools validate and check documents, describe and edit them by
id, draw them and export wire lists and bills of materials. Their results carry two links for the user: one opens
the drawing in the [web editor](https://uniwire.sh/viewer/), the other is the PDF.

**ChatGPT**: uniwire is in ChatGPT's plugin directory. Open [uniwire in ChatGPT](https://chatgpt.com/plugins/plugin_asdk_app_6ace27d31ab08191b243ec37826969c2), choose *Try in chat*,
then mention `@uniwire` in a conversation. Nothing to configure, no developer mode.

**Claude** (claude.ai and Claude Desktop): Settings, Connectors, *Add custom connector*, paste the URL above.

**Claude Code**

```bash
claude mcp add --transport http uniwire https://mcp.uniwire.sh/mcp
```

**Cursor**: [Add to Cursor](cursor://anysphere.cursor-deeplink/mcp/install?name=uniwire&config=eyJ1cmwiOiJodHRwczovL21jcC51bml3aXJlLnNoL21jcCJ9){ .md-button }
or in `.cursor/mcp.json`:

```json
{"mcpServers": {"uniwire": {"url": "https://mcp.uniwire.sh/mcp"}}}
```

**VS Code**: [Install in VS Code](vscode:mcp/install?%7B%22name%22%3A%22uniwire%22%2C%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fmcp.uniwire.sh%2Fmcp%22%7D){ .md-button }
or in `.vscode/mcp.json`:

```json
{"servers": {"uniwire": {"type": "http", "url": "https://mcp.uniwire.sh/mcp"}}}
```

**Other clients**: any client that speaks streamable HTTP takes the URL above.

The hosted server bounds every call (document size, sheets, time; see [Public server](llm.md#public-server)) and
keeps the documents of its results for 30 days so that the links it returns stay short
([Short links](llm.md#short-links)). It logs which tool was called, the outcome and the duration. Like every request
to uniwire.sh, the request itself is kept with the caller's address in the security logs for one year
([privacy](https://uniwire.sh/privacy)).

## No MCP: any assistant that reads web pages

Tell the assistant to read [uniwire.sh/llms.txt](https://uniwire.sh/llms.txt) and follow it. The page holds the
whole reference card of the format: the assistant writes the document itself and, if it can run Python, gives
you a link that opens it in the web editor, where the library draws and checks it in your browser. The link
sends nothing to uniwire.sh: the document travels in the part of the link after `#`.

```text
Read https://uniwire.sh/llms.txt and follow it to draw the single-line diagram of a small bakery:
three-phase 400 V, 12 kW oven, 3 kW kneader, cold room, lighting, sockets.
```

## Local: your own server

For private documents or offline work, run the server on your machine (`pip install "uniwire[mcp,pdf]"`, then
`uniwire-mcp`). Setup for Claude Code, Claude Desktop and other clients: [MCP server](llm.md#mcp-server).

## What it draws

uniwire draws power distribution: single-line and multi-line diagrams, from the sources to the loads, with
protections, cables and RCDs, plus rule checks, bills of materials and wire lists. It does not draw control
schematics (relay coils and contacts, push buttons, signal lamps, current paths). Asked for one, the assistant
should say so and offer the power side of the installation; when a document describes control circuits, `check`
says so too (`core.scope`, see [Rules](rules.md)).

## Example requests

- *Fais-moi le schéma unifilaire d'un appartement de 60 m² en monophasé, régime TT, et vérifie-le selon la NF C 15-100.*
- *Draw the single-line diagram of a small office: 3-phase 400 V, 12 desks, server rack on a UPS, air conditioning.*
- *Vérifie ce tableau : le disjoncteur 32 A du four est-il compatible avec un câble de 4 mm² ?*
- *Add a 7 kW EV charger to this installation and give me the updated PDF.*
- *Liste des fils et des repères pour le câblage de ce tableau.*
