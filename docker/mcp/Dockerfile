# Official uniwire MCP server image (ghcr.io/uniwire-dev/uniwire-mcp).
#
# Build from the repository root:
#     docker build -f docker/mcp/Dockerfile -t uniwire-mcp .
# Run (public HTTP mode: no file system access, bounded inputs and outputs, document tools in worker
# processes with a timeout; see docs/llm.md, "Public server"):
#     docker run --rm -p 8000:8000 --read-only --tmpfs /tmp --cap-drop ALL uniwire-mcp --allowed-host localhost
# The endpoint is http://localhost:8000/mcp; GET /healthz answers 200.
#
# Base image: python:3.15-slim, pinned by digest (update both FROM lines together).

FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE CHANGELOG.md ./
COPY src/ src/
COPY examples/ examples/
RUN pip install --no-cache-dir "build>=1.2" && python -m build --wheel --outdir /dist

FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce
LABEL org.opencontainers.image.title="uniwire-mcp" \
      org.opencontainers.image.description="MCP server for uniwire documents (electrical installations)" \
      org.opencontainers.image.source="https://github.com/uniwire-dev/uniwire" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
# Liberation Sans for the PDF output: Arial widths, with the Greek letters and symbols of the drawings (Ω, Δ, ≤, →)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY --from=build /dist/ /tmp/dist/
RUN pip install --no-cache-dir "$(ls /tmp/dist/uniwire-*.whl)[mcp,pdf]" && rm -rf /tmp/dist
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
ENTRYPOINT ["uniwire-mcp", "--http", "--public", "--host", "0.0.0.0", "--port", "8000"]
